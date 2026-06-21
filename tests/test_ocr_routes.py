"""Integration tests for the OCR extract route (POST /ocr/extract).

纯识别端点：上传 / 目录 → 确定性识别底稿。用 native 文件（txt）测，不依赖
paddleocr；扫描件 OCR 引擎路径需部署 serving，不在单测覆盖。
"""

from __future__ import annotations

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from server.routes.upload_helpers import tenant_submission_root

_TOKEN = "test-fake-token-acme-ocr"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
_CASE_ROOT = tenant_submission_root("acme")  # 测试租户提交子树根（F2 隔离边界）


@pytest.fixture
def client(monkeypatch):
    """TestClient with a patched tenant key (no default-key 503 guard)."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"acme": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    return TestClient(api_module.app)


def test_extract_upload_native_text_returns_results(client):
    files = [("files", ("note.txt", "报销说明：差旅费 880 元".encode(), "text/plain"))]
    resp = client.post("/ocr/extract", files=files, headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["request_id"]
    assert len(body["results"]) == 1
    item = body["results"][0]
    assert item["kind"] == "text"
    assert item["route"] == "native"
    assert "差旅费" in body["block"]


def test_extract_upload_single_file_field(client):
    """支持单 `file` 字段(besides files[])——单文件 multipart 上传（用户需求 #29）。"""
    files = [("file", ("single.txt", "单文件字段内容".encode(), "text/plain"))]
    resp = client.post("/ocr/extract", files=files, headers=_AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["results"]) == 1
    assert "单文件字段内容" in body["block"]


def test_extract_multiple_files(client):
    files = [
        ("files", ("a.txt", b"first file", "text/plain")),
        ("files", ("b.txt", b"second file", "text/plain")),
    ]
    resp = client.post("/ocr/extract", files=files, headers=_AUTH)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 2


def test_extract_unknown_type_marked_manual(client):
    # 不在白名单的扩展名 → classify 判 manual，不报错也不调引擎。
    files = [("files", ("weird.xyz", b"opaque bytes", "application/octet-stream"))]
    resp = client.post("/ocr/extract", files=files, headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["results"][0]["kind"] == "manual"


def test_extract_requires_auth(client):
    files = [("files", ("a.txt", b"x", "text/plain"))]
    resp = client.post("/ocr/extract", files=files)  # no Authorization header
    assert resp.status_code == 401


def test_extract_empty_upload_rejected(client):
    # multipart 但没有 files 字段 → 400
    resp = client.post(
        "/ocr/extract",
        files=[("other", ("x.txt", b"x", "text/plain"))],
        headers=_AUTH,
    )
    assert resp.status_code == 400


def test_extract_directory_mode(client):
    case = _CASE_ROOT / "ocr" / "test-ocr-route-case"
    case.mkdir(parents=True, exist_ok=True)
    (case / "doc.txt").write_text("目录模式识别内容", encoding="utf-8")
    try:
        resp = client.post(
            "/ocr/extract",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["kind"] == "text"
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_extract_directory_outside_root_rejected(client):
    resp = client.post(
        "/ocr/extract",
        json={"mode": "directory", "directory_path": "/etc"},
        headers=_AUTH,
    )
    assert resp.status_code == 400


def test_extract_directory_cross_tenant_rejected(client):
    # round4 F2 / approach b 核心：acme 不能 directory-读其他租户的提交子树。
    other = tenant_submission_root("other-tenant") / "case"
    other.mkdir(parents=True, exist_ok=True)
    (other / "doc.txt").write_text("OTHER TENANT DATA", encoding="utf-8")
    try:
        resp = client.post(
            "/ocr/extract",
            json={"mode": "directory", "directory_path": str(other)},
            headers=_AUTH,
        )
        assert resp.status_code == 400  # 跨租户子树被拒
    finally:
        shutil.rmtree(other, ignore_errors=True)


def test_tenant_submission_root_rejects_traversal_names():
    # review F1：含 / 或 .. / 空的 tenant 名不得让 resolve 逃出 submissions 根。
    from fastapi import HTTPException

    for bad in ["../etc", "a/b", "..", "", "x" * 65]:
        with pytest.raises(HTTPException):
            tenant_submission_root(bad)
    assert tenant_submission_root("acme").name == "acme"  # 合法名通过


def test_extract_unsupported_content_type(client):
    resp = client.post(
        "/ocr/extract",
        content=b"raw payload",
        headers={**_AUTH, "Content-Type": "text/plain"},
    )
    assert resp.status_code == 415


# ── /ocr/fill（识别 + 表单回填，映射阶段 mock 掉模型）─────────────────────────


def test_fill_returns_recognized_and_filled(client, monkeypatch):
    async def fake_map(block, form_schema, *, request_id, tenant=None, **opts):
        assert "差旅" in block  # 真实识别底稿确实喂进了映射
        return {
            "fields": [{"key": "项目名称", "component": "single_line", "value": "X", "confidence": 0.9}],
            "sub_tables": [],
            "needs_review": False,
        }

    monkeypatch.setattr("server.routes.ocr.map_extraction_to_form", fake_map)
    files = [("files", ("note.txt", "差旅费 880 元".encode(), "text/plain"))]
    data = {"form_schema": json.dumps({"fields": [{"key": "项目名称", "component": "single_line"}]})}
    resp = client.post("/ocr/fill", files=files, data=data, headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["kind"] == "text"  # 左栏底稿来自真实识别
    assert "block" in body
    assert body["fill"]["fields"][0]["key"] == "项目名称"  # 右栏回填来自映射


def test_fill_without_schema_uses_adaptive_mode(client, monkeypatch):
    """缺 form_schema → 自适应抽取（不再 400）：以空 schema 调映射，字段集由文档决定。"""
    seen: dict[str, object] = {}

    async def fake_map(block, form_schema, *, request_id, tenant=None, **opts):
        seen["schema"] = form_schema
        return {
            "fields": [{"key": "合同金额", "component": "number", "value": 880, "confidence": 0.9}],
            "sub_tables": [],
            "needs_review": False,
        }

    monkeypatch.setattr("server.routes.ocr.map_extraction_to_form", fake_map)
    files = [("files", ("note.txt", "差旅费 880 元".encode(), "text/plain"))]
    resp = client.post("/ocr/fill", files=files, headers=_AUTH)  # 缺 form_schema → 自适应
    assert resp.status_code == 200
    assert seen["schema"] == {}  # 空 schema 透传 → 触发自适应分支
    assert resp.json()["fill"]["fields"][0]["key"] == "合同金额"


def test_fill_rejects_invalid_form_schema(client):
    files = [("files", ("a.txt", b"x", "text/plain"))]
    resp = client.post("/ocr/fill", files=files, data={"form_schema": "not-json"}, headers=_AUTH)
    assert resp.status_code == 400


def test_fill_requires_auth(client):
    files = [("files", ("a.txt", b"x", "text/plain"))]
    resp = client.post("/ocr/fill", files=files, data={"form_schema": "{}"})  # 无 token
    assert resp.status_code == 401


# ── codex review round 1 修复回归 ─────────────────────────────────────────────


def test_extract_malformed_json_returns_400(client):
    # 畸形 JSON 应返 400（client error），而非 500（曾因 JSONDecodeError 逃逸到 generic handler）。
    resp = client.post(
        "/ocr/extract",
        content=b"{not valid json",
        headers={**_AUTH, "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_extract_duplicate_filenames_both_preserved(client):
    # 两个同名文件不能互相覆盖，否则 results 少一条、回填底稿不全。
    files = [
        ("files", ("scan.txt", b"first content", "text/plain")),
        ("files", ("scan.txt", b"second content", "text/plain")),
    ]
    resp = client.post("/ocr/extract", files=files, headers=_AUTH)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 2


def test_extract_result_path_is_basename_not_absolute(client):
    # 出口投影：upload 模式 path 只暴露文件名，不泄露 host 绝对路径。
    files = [("files", ("note.txt", b"hi", "text/plain"))]
    resp = client.post("/ocr/extract", files=files, headers=_AUTH)
    assert resp.status_code == 200
    path = resp.json()["results"][0]["path"]
    assert path == "note.txt"
    assert not path.startswith("/")


def test_extract_directory_preserves_subdir_paths(client):
    # codex round 2：directory 模式有子目录同名文件时，path 须保留相对路径以区分，
    # 不能塌成 basename（否则 a/doc.txt 与 b/doc.txt 无法区分）。
    case = _CASE_ROOT / "ocr" / "test-ocr-subdir-case"
    (case / "a").mkdir(parents=True, exist_ok=True)
    (case / "b").mkdir(parents=True, exist_ok=True)
    (case / "a" / "doc.txt").write_text("AAA", encoding="utf-8")
    (case / "b" / "doc.txt").write_text("BBB", encoding="utf-8")
    try:
        resp = client.post(
            "/ocr/extract",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        assert resp.status_code == 200
        paths = sorted(r["path"] for r in resp.json()["results"])
        assert paths == ["a/doc.txt", "b/doc.txt"]
    finally:
        shutil.rmtree(case, ignore_errors=True)


def test_extract_corrupt_file_isolated_as_error(client):
    # codex round 3：损坏 xlsx（非法 zip）应标 kind=error 隔离，不让整批 500（per-file 隔离）。
    files = [
        ("files", ("good.txt", b"ok content", "text/plain")),
        (
            "files",
            (
                "bad.xlsx",
                b"not a real xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
    ]
    resp = client.post("/ocr/extract", files=files, headers=_AUTH)
    assert resp.status_code == 200
    kinds = {r["path"]: r["kind"] for r in resp.json()["results"]}
    assert kinds["good.txt"] == "text"
    assert kinds["bad.xlsx"] == "error"


def test_extract_directory_rejects_symlink_escape(client, tmp_path):
    # codex round 4 P1：directory 模式不得经子 symlink 读 case 目录外的文件。
    case = _CASE_ROOT / "ocr" / "test-ocr-symlink-case"
    case.mkdir(parents=True, exist_ok=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET_OUTSIDE_DATA", encoding="utf-8")
    (case / "normal.txt").write_text("ok", encoding="utf-8")
    (case / "link.txt").symlink_to(secret)
    try:
        resp = client.post(
            "/ocr/extract",
            json={"mode": "directory", "directory_path": str(case)},
            headers=_AUTH,
        )
        assert resp.status_code == 200
        body = resp.json()
        paths = [r["path"] for r in body["results"]]
        assert "normal.txt" in paths
        assert "link.txt" not in paths  # symlink 被跳过，不识别
        assert "SECRET_OUTSIDE_DATA" not in body["block"]  # 目标内容未泄露
    finally:
        shutil.rmtree(case, ignore_errors=True)
