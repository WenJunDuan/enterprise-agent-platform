"""Upload and directory path helpers for audit submission endpoints.

Pure helper functions for: form-data parsing, file upload materialisation,
directory path validation, and case-path serialisation.
No route handlers, no FastAPI app references.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from server.platform.config import get_app_settings
from server.platform.paths import PROJECT_ROOT, SUBMISSION_ROOT_DIR
from server.platform.storage import append_json_file

# tenant 名白名单：阻止含 / 或 .. 的名字让 resolve 逃出 submissions 根（round4 F2 / review F1）。
_SAFE_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def tenant_submission_root(tenant: str) -> Path:
    """每租户提交子树根 ``data/submissions/<tenant>/``（round4 F2 隔离边界）。

    对 tenant 名做白名单校验——含 ``/`` / ``..`` / 空串的名字会让 ``resolve`` 逃出
    submissions 根、破坏隔离（防御内部威胁：被污染的 TENANT_KEYS 配置）。非法名直接拒，
    不静默穿越。
    """
    if not _SAFE_TENANT.match(tenant):
        raise HTTPException(status_code=400, detail="invalid tenant identifier")
    return (SUBMISSION_ROOT_DIR / tenant).resolve()


def serialize_case_path(path: Path) -> str:
    """Return a project-relative path string, or absolute if outside project root."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def validate_directory_case_path(case_path: str, tenant: str) -> str:
    """Validate *case_path* exists, is a directory, inside the tenant's submissions subtree.

    round4 F2：directory 模式原仅校验"在 data/ 下"，可读 data/db / data/sessions / 跨租户提交。
    现限定在 ``data/submissions/<tenant>/`` 子树（隐式校验归属）——服务内部目录与他租户数据均不可达。
    """
    path = Path(case_path)
    if not path.exists() or not path.is_dir():
        raise HTTPException(
            status_code=400, detail="directory_path must point to an existing directory"
        )
    resolved = path.resolve()
    try:
        resolved.relative_to(tenant_submission_root(tenant))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="directory_path is outside the tenant submissions root"
        ) from exc
    return serialize_case_path(resolved)


def remove_submission_dir(case_path: str | None) -> None:
    """Delete an uploaded submission directory, but only under the submissions root."""
    if not case_path:
        return
    candidate = Path(case_path)
    resolved = (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()
    submissions_root = SUBMISSION_ROOT_DIR.resolve()
    if submissions_root not in resolved.parents:
        return
    shutil.rmtree(resolved, ignore_errors=True)


def sanitize_upload_name(name: str, index: int) -> str:
    """Strip directory components from an uploaded filename; raise 400 if empty."""
    sanitized = Path(name).name
    if not sanitized:
        raise HTTPException(status_code=400, detail=f"File {index} is missing a filename")
    return sanitized


def validate_upload_bytes(content: bytes) -> None:
    """Raise 400 if *content* is empty or exceeds the configured size limit."""
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file cannot be empty")
    if len(content) > get_app_settings().max_upload_file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file exceeds size limit")


def _append_form_field(fields: dict[str, Any], key: str, value: str) -> None:
    current = fields.get(key)
    if current is None:
        fields[key] = value
    elif isinstance(current, list):
        current.append(value)
    else:
        fields[key] = [current, value]


def collect_scalar_form_fields(form_data: Any) -> dict[str, Any]:
    """Extract non-file, non-reserved scalar fields from multipart form data."""
    fields: dict[str, Any] = {}
    iterator = form_data.multi_items() if hasattr(form_data, "multi_items") else form_data.items()
    for key, value in iterator:
        field_name = str(key)
        if field_name in {"mode", "form_json", "files"}:
            continue
        if hasattr(value, "filename"):
            continue
        _append_form_field(fields, field_name, str(value))
    return fields


def parse_optional_form_json(form_json: str | None) -> dict[str, Any]:
    """Parse the optional *form_json* field; raise 400 on malformed JSON."""
    normalized = str(form_json or "").strip()
    if not normalized:
        return {}
    try:
        parsed_form = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid form_json") from exc
    if not isinstance(parsed_form, dict):
        raise HTTPException(status_code=400, detail="form_json must decode to a JSON object")
    return parsed_form


async def materialize_upload_submission(
    *,
    request_id: str,
    tenant: str,
    form_json: str | None,
    form_data: Any,
) -> str:
    """Write uploaded files and form metadata to the tenant's submission directory.

    Returns the serialized case path (project-relative string).
    """
    parsed_form = parse_optional_form_json(form_json)
    scalar_fields = collect_scalar_form_fields(form_data)
    files = form_data.getlist("files")
    if not parsed_form and not scalar_fields and not files:
        raise HTTPException(
            status_code=400, detail="upload mode requires form_json, form fields, or files"
        )

    case_dir = SUBMISSION_ROOT_DIR / tenant / request_id
    case_dir.mkdir(parents=True, exist_ok=True)

    attachments: list[dict[str, Any]] = []
    try:
        for index, upload in enumerate(files, start=1):
            safe_name = sanitize_upload_name(getattr(upload, "filename", "") or "", index)
            target_path = case_dir / safe_name
            content = await upload.read()
            validate_upload_bytes(content)
            target_path.write_bytes(content)
            attachments.append(
                {"type": "uploaded", "name": safe_name, "path": serialize_case_path(target_path)}
            )

        append_json_file(
            case_dir / "audit-request.json",
            {"form": parsed_form, "fields": scalar_fields, "attachments": attachments},
        )
    except Exception:
        shutil.rmtree(case_dir, ignore_errors=True)
        raise

    return serialize_case_path(case_dir)


async def materialize_ocr_upload(*, request_id: str, tenant: str, files: list[Any]) -> str:
    """Write uploaded files (no metadata sidecar) to the tenant's submission directory.

    与 materialize_upload_submission 的区别：OCR 纯识别只需要原始文件，**不写**
    audit-request.json —— 否则该 sidecar 会被 extract_dir 当成待识别文件，污染结果。

    Returns the serialized case path (project-relative string).
    """
    if not files:
        raise HTTPException(status_code=400, detail="ocr extract requires at least one file")
    case_dir = SUBMISSION_ROOT_DIR / tenant / request_id
    case_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    try:
        for index, upload in enumerate(files, start=1):
            safe_name = sanitize_upload_name(getattr(upload, "filename", "") or "", index)
            # 同名文件（如不同文件夹各一个 scan.pdf）加序号，防后者覆盖前者导致结果丢失。
            if safe_name in used_names:
                stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
                safe_name = f"{stem}_{index}{suffix}"
            used_names.add(safe_name)
            content = await upload.read()
            validate_upload_bytes(content)
            (case_dir / safe_name).write_bytes(content)
    except Exception:
        shutil.rmtree(case_dir, ignore_errors=True)
        raise
    return serialize_case_path(case_dir)
