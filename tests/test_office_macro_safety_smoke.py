from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "scripts" / "document_format_fixtures" / "macro-on-open.odt"
VERIFY_SCRIPT = PROJECT_ROOT / "scripts" / "verify_office_macro_safety.py"


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
def test_real_macro_document_cannot_create_side_effect_and_leaves_no_process(tmp_path):
    evidence_path = tmp_path / "office-macro-safety.json"
    result = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--fixture",
            str(FIXTURE),
            "--evidence",
            str(evidence_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "ok"
    assert evidence["execution_scope"] == (
        f"current runtime: {platform.system()} {platform.machine()}"
    )
    assert evidence["fixture_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert evidence["macro_present"] is True
    assert evidence["side_effect_created"] is False
    assert evidence["profile_removed"] is True
    assert evidence["residual_processes"] == []
