#!/usr/bin/env python3
"""Prove that a macro-bearing ODT converts without macro side effects or residue."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.ocr.office_convert import convert_office_to_pdf  # noqa: E402


def _office_processes() -> dict[int, str]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    processes: dict[int, str] = {}
    for line in completed.stdout.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2 or not fields[0].isdigit():
            continue
        command = fields[1]
        executable = Path(command.split(maxsplit=1)[0]).name.lower()
        if executable in {"soffice", "soffice.bin", "libreoffice"}:
            processes[int(fields[0])] = command
    return processes


def _inspect_macro(fixture: Path) -> dict[str, bool]:
    with zipfile.ZipFile(fixture) as archive:
        names = set(archive.namelist())
        module = archive.read("Basic/Standard/Module1.xml").decode("utf-8")
        content = archive.read("content.xml").decode("utf-8")
    return {
        "macro_present": "Basic/Standard/Module1.xml" in names and "Sub Main" in module,
        "side_effect_code_present": "macro-side-effect.txt" in module and "Open markerPath" in module,
        "load_event_present": "script:event-listener" in content and "dom:load" in content,
    }


def verify(fixture: Path) -> dict[str, object]:
    """Convert a macro-bearing fixture and report isolation and residue evidence."""
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if executable is None:
        raise RuntimeError("LibreOffice is not installed")
    macro = _inspect_macro(fixture)
    if not all(macro.values()):
        raise RuntimeError(f"fixture does not contain the required macro and load event: {macro}")

    version = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    ).stdout.strip()
    before = _office_processes()
    profile_path: Path | None = None
    temp_root: Path | None = None
    pdf_magic = ""
    side_effect_created = False
    with convert_office_to_pdf(fixture) as pdf:
        temp_root = pdf.parent.parent
        profile_path = temp_root / "profile"
        pdf_magic = pdf.read_bytes()[:5].decode("ascii", "replace")
        side_effect_created = (temp_root / "input" / "macro-side-effect.txt").exists()
        if not profile_path.is_dir():
            raise RuntimeError("isolated LibreOffice profile was not created")

    assert temp_root is not None and profile_path is not None
    for _ in range(20):
        after = _office_processes()
        residual = {pid: command for pid, command in after.items() if pid not in before}
        if not residual:
            break
        time.sleep(0.1)
    profile_removed = not profile_path.exists() and not temp_root.exists()
    system = platform.system()
    architecture = platform.machine()
    evidence: dict[str, object] = {
        "status": "ok",
        "executed_at": datetime.now(UTC).isoformat(),
        "execution_scope": f"current runtime: {system} {architecture}",
        "host": {"system": system, "architecture": architecture},
        "libreoffice_version": version,
        "fixture": str(fixture.resolve()),
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        **macro,
        "pdf_magic": pdf_magic,
        "side_effect_created": side_effect_created,
        "profile_removed": profile_removed,
        "residual_processes": [
            {"pid": pid, "command": command} for pid, command in sorted(residual.items())
        ],
    }
    if (
        pdf_magic != "%PDF-"
        or side_effect_created
        or not profile_removed
        or evidence["residual_processes"]
    ):
        evidence["status"] = "failed"
    return evidence


def main() -> int:
    """Persist macro-safety evidence and return a shell-friendly status code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = verify(args.fixture.resolve())
    except Exception as error:  # noqa: BLE001 - CLI must persist diagnostic evidence
        evidence = {
            "status": "failed",
            "executed_at": datetime.now(UTC).isoformat(),
            "error": f"{type(error).__name__}: {error}",
        }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
