from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "shared" / "supported-document-formats.json"
GENERATED_PATH = (
    PROJECT_ROOT
    / "agent-front"
    / "src"
    / "features"
    / "contract"
    / "tender-review"
    / "supported-document-formats.ts"
)
EXPECTED_GROUPS = {
    "text": [".txt", ".csv", ".md", ".json", ".tsv"],
    "images": [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"],
    "word_native": [".docx"],
    "word_legacy": [".doc"],
    "excel_ooxml": [".xlsx", ".xlsm"],
    "excel_xls": [".xls"],
    "excel_xlsb": [".xlsb"],
    "presentation_native": [".pptx"],
    "office_convert": [".ppt", ".odt", ".ods", ".odp"],
    "pdf": [".pdf"],
}


def test_manifest_is_the_complete_unique_format_contract() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest == {"version": 1, "groups": EXPECTED_GROUPS}
    extensions = [suffix for suffixes in manifest["groups"].values() for suffix in suffixes]
    assert len(extensions) == len(set(extensions))
    assert ".heic" not in extensions
    assert all(suffix.startswith(".") and suffix == suffix.lower() for suffix in extensions)


def test_frontend_generated_contract_has_no_drift() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_document_formats.py", "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    generated = GENERATED_PATH.read_text(encoding="utf-8")
    assert "image/*" not in generated
    assert ".heic" not in generated


def test_upload_components_only_use_the_generated_accept_constant() -> None:
    component_dir = (
        PROJECT_ROOT
        / "agent-front"
        / "src"
        / "features"
        / "contract"
        / "tender-review"
        / "components"
    )

    for name in ("create-review-view.tsx", "dashboard-view.tsx"):
        source = (component_dir / name).read_text(encoding="utf-8")
        assert "accept={ACCEPTED_DOCUMENT_FILE_TYPES}" in source
        assert "ACCEPTED_REVIEW_FILE_TYPES" not in source
        assert "ACCEPTED_BIDDER_FILE_TYPES" not in source
        assert "image/*" not in source
        assert ".heic" not in source


def test_backend_images_copy_manifest_and_install_full_document_dependencies() -> None:
    expected_python = {
        "xlrd==2.0.2",
        "pyxlsb==1.0.10",
        "python-pptx==1.0.2",
        "Pillow==12.3.0",
        "pdfplumber==0.11.10",
        "paddlepaddle==3.2.2",
        '"paddleocr[doc-parser]==3.7.0"',
        "paddlex==3.7.2",
    }
    expected_apt = {
        "libreoffice-writer",
        "libreoffice-calc",
        "libreoffice-impress",
        "tesseract-ocr",
        "tesseract-ocr-chi-sim",
        "tesseract-ocr-eng",
        "antiword",
        "fonts-noto-cjk",
        "fonts-liberation2",
    }

    for relative_path in ("Dockerfile", "agent-front/deploy/Containerfile.agent-backend"):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "COPY --chown=app:app shared ./shared" in source
        assert "scripts/generate_document_formats.py" in source
        assert "scripts/smoke_document_formats.py" in source
        assert "scripts/verify_office_macro_safety.py" in source
        assert "scripts/document_format_fixtures" in source
        for dependency in expected_python | expected_apt:
            assert dependency in source, f"{relative_path} is missing {dependency}"

    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"Pillow==12.3.0"' in pyproject


def test_demo_runbook_syncs_scripts_and_fails_closed_on_smoke_pipeline() -> None:
    runbook = (PROJECT_ROOT / "deploy" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")

    assert "`scripts/`" in runbook
    assert "set -o pipefail" in runbook
    assert "document-format-smoke.json" in runbook
    assert 'payload["status"] == "ok"' in runbook
    assert "PIPESTATUS[0]" in runbook


def test_docker_context_excludes_runtime_test_and_archive_content() -> None:
    patterns = set(
        line.strip()
        for line in (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )

    assert {
        ".git",
        ".ai_state",
        "tests",
        "logs",
        "data",
        "knowledge",
        "backups",
        "docker-export",
        ".venv",
        "agent-front/node_modules",
        ".env*",
        "**/__pycache__",
        "*.tar.gz",
    } <= patterns
