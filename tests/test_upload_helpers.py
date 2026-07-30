"""存储结构改造：build_case_dir 路径 + validate_directory_case_path 域/根安全（codex P1.2/P1.3）。"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import FormData, UploadFile

from server.routes.upload_helpers import (
    UNBOUND_PROJECT,
    build_case_dir,
    materialize_upload_submission,
    tenant_submission_root,
    validate_document_upload,
    validate_directory_case_path,
)


# ── build_case_dir 路径构造 ────────────────────────────────────────────────────


def test_build_case_dir_audit_ocr_flat():
    root = tenant_submission_root("acme")
    assert build_case_dir("acme", "audit", "rid1") == root / "audit" / "rid1"
    assert build_case_dir("acme", "ocr", "rid2") == root / "ocr" / "rid2"


def test_build_case_dir_tender_with_project():
    root = tenant_submission_root("acme")
    assert build_case_dir("acme", "tender", "rid3", "tp-abc") == root / "tender" / "tp-abc" / "rid3"


def test_build_case_dir_rejects_unknown_domain():
    with pytest.raises(HTTPException) as exc:
        build_case_dir("acme", "evil", "rid")
    assert exc.value.status_code == 400


def test_build_case_dir_tender_requires_project():
    # codex P2：tender 必须带 project 层。
    with pytest.raises(HTTPException) as exc:
        build_case_dir("acme", "tender", "rid")  # 无 project_id
    assert exc.value.status_code == 400


def test_build_case_dir_audit_ocr_reject_project():
    # codex P2：audit/ocr 不得带 project_id（否则造出 maintenance 不识别的形状）。
    with pytest.raises(HTTPException):
        build_case_dir("acme", "audit", "rid", "tp-x")
    with pytest.raises(HTTPException):
        build_case_dir("acme", "ocr", "rid", "tp-x")


def test_build_case_dir_rejects_traversal_segment():
    # request_id / project_id 含 / 或 .. → 白名单拒，防穿越。
    with pytest.raises(HTTPException):
        build_case_dir("acme", "tender", "../escape", "tp-x")
    with pytest.raises(HTTPException):
        build_case_dir("acme", "tender", "rid", "../escape")


def test_unbound_project_passes_whitelist():
    # codex P1.1：sentinel 无前导下划线，过白名单（否则 legacy tender 建目录会 400）。
    root = tenant_submission_root("acme")
    assert build_case_dir("acme", "tender", "rid", UNBOUND_PROJECT) == root / "tender" / "unbound" / "rid"


def test_document_upload_rejects_unknown_extension_and_spoofed_magic():
    with pytest.raises(HTTPException, match="Unsupported document format"):
        validate_document_upload("payload.exe", b"MZ fake executable")
    with pytest.raises(HTTPException, match="does not match"):
        validate_document_upload("spoofed.pdf", b"MZ fake executable")
    with pytest.raises(HTTPException, match="does not match"):
        validate_document_upload("generic.docx", b"PK\x03\x04not-a-real-package")


def test_document_upload_accepts_unicode_text_but_rejects_binary_text():
    validate_document_upload("清单.csv", "项目,金额\n服务,880\n".encode())
    validate_document_upload("说明.txt", "中文底稿\n第二行".encode("gb18030"))

    with pytest.raises(HTTPException, match="does not match"):
        validate_document_upload("binary.txt", b"valid-prefix\x00binary-tail")


async def test_document_validation_is_opt_in_for_shared_audit_helper(tmp_path, monkeypatch):
    monkeypatch.setattr("server.routes.upload_helpers.SUBMISSION_ROOT_DIR", tmp_path)
    upload = UploadFile(file=io.BytesIO(b"domain-specific payload"), filename="custom.xyz")
    form = FormData([("files", upload), ("mode", "upload")])

    case_path = await materialize_upload_submission(
        request_id="audit-case",
        tenant="acme",
        form_json=None,
        form_data=form,
        domain="audit",
    )

    assert (Path(case_path) / "custom.xyz").read_bytes() == b"domain-specific payload"


async def test_document_validation_opt_in_rejects_tender_bypass(tmp_path, monkeypatch):
    monkeypatch.setattr("server.routes.upload_helpers.SUBMISSION_ROOT_DIR", tmp_path)
    upload = UploadFile(file=io.BytesIO(b"MZ fake executable"), filename="bypass.exe")
    form = FormData([("files", upload)])

    with pytest.raises(HTTPException, match="Unsupported document format"):
        await materialize_upload_submission(
            request_id="tender-case",
            tenant="acme",
            form_json=None,
            form_data=form,
            domain="tender",
            project_id="tp-test",
            validate_document_format=True,
        )

    assert not (tmp_path / "acme" / "tender" / "tp-test" / "tender-case").exists()


# ── validate_directory_case_path 域/根安全 ─────────────────────────────────────


def test_validate_rejects_wrong_domain(tmp_path, monkeypatch):
    """codex P1.3：audit 路由不能读 tender 子树（同租户跨域隔离）。"""
    monkeypatch.setattr("server.routes.upload_helpers.SUBMISSION_ROOT_DIR", tmp_path)
    # 在 tender 子树建目录，却用 expected_domain="audit" 校验 → 拒。
    case = tmp_path / "acme" / "tender" / "tp-x" / "rid"
    case.mkdir(parents=True)
    with pytest.raises(HTTPException) as exc:
        validate_directory_case_path(str(case), "acme", expected_domain="audit")
    assert exc.value.status_code == 400


def test_validate_rejects_domain_root(tmp_path, monkeypatch):
    """domain 根目录本身不是案件目录 → 拒（必须更深一层）。"""
    monkeypatch.setattr("server.routes.upload_helpers.SUBMISSION_ROOT_DIR", tmp_path)
    domain_root = tmp_path / "acme" / "audit"
    domain_root.mkdir(parents=True)
    with pytest.raises(HTTPException):
        validate_directory_case_path(str(domain_root), "acme", expected_domain="audit")


def test_validate_accepts_correct_domain_case(tmp_path, monkeypatch):
    monkeypatch.setattr("server.routes.upload_helpers.SUBMISSION_ROOT_DIR", tmp_path)
    case = tmp_path / "acme" / "audit" / "rid"
    case.mkdir(parents=True)
    result = validate_directory_case_path(str(case), "acme", expected_domain="audit")
    assert "audit" in result and "rid" in result


def test_validate_tender_project_subtree(tmp_path, monkeypatch):
    """tender 校验可收紧到具体 project 子树。"""
    monkeypatch.setattr("server.routes.upload_helpers.SUBMISSION_ROOT_DIR", tmp_path)
    case = tmp_path / "acme" / "tender" / "tp-x" / "rid"
    case.mkdir(parents=True)
    # 正确 project → 通过
    validate_directory_case_path(
        str(case), "acme", expected_domain="tender", expected_project_id="tp-x"
    )
    # 错误 project → 拒
    with pytest.raises(HTTPException):
        validate_directory_case_path(
            str(case), "acme", expected_domain="tender", expected_project_id="tp-other"
        )
