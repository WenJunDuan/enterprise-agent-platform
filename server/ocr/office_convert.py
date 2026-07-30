"""Bounded, defensive LibreOffice-to-PDF conversion."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from server.ocr import OcrDependencyError
from server.ocr.formats import suffixes

DEFAULT_TIMEOUT_SEC = 90
DEFAULT_MAX_OUTPUT_BYTES = 536_870_912
_CONVERTIBLE_SUFFIXES = suffixes("office_convert") | suffixes("word_native") | suffixes(
    "word_legacy"
) | suffixes("excel_ooxml") | suffixes("excel_xls") | suffixes(
    "excel_xlsb"
) | suffixes("presentation_native")


def _env_positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


OCR_OFFICE_TIMEOUT_SEC = _env_positive_int("OCR_OFFICE_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC)
OCR_OFFICE_MAX_OUTPUT_BYTES = _env_positive_int(
    "OCR_OFFICE_MAX_OUTPUT_BYTES", DEFAULT_MAX_OUTPUT_BYTES
)
OCR_OFFICE_MAX_INPUT_BYTES = _env_positive_int("OCR_MAX_TEMP_BYTES", DEFAULT_MAX_OUTPUT_BYTES)
_OFFICE_SEMAPHORE = threading.BoundedSemaphore(
    _env_positive_int("OCR_OFFICE_MAX_CONCURRENCY", 1)
)


def _write_macro_security_profile(profile: Path) -> None:
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "registrymodifications.xcu").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
 <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
  <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
  <prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
 </item>
</oor:items>
""",
        encoding="utf-8",
    )


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _validated_pdf(output_dir: Path, stem: str) -> Path:
    pdf = output_dir / f"{stem}.pdf"
    try:
        resolved = pdf.resolve(strict=True)
        resolved.relative_to(output_dir.resolve())
    except (OSError, ValueError) as exc:
        raise OcrDependencyError("LibreOffice produced no safe PDF output") from exc
    if pdf.is_symlink() or not resolved.is_file():
        raise OcrDependencyError("LibreOffice PDF output is not a regular file")
    size = resolved.stat().st_size
    if size > OCR_OFFICE_MAX_OUTPUT_BYTES:
        raise OcrDependencyError("LibreOffice PDF output exceeds configured byte limit")
    with resolved.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise OcrDependencyError("LibreOffice output failed PDF magic validation")
    return resolved


@contextmanager
def convert_office_to_pdf(path: Path) -> Iterator[Path]:
    """Yield a validated temporary PDF and clean all conversion state on exit."""
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in _CONVERTIBLE_SUFFIXES:
        raise OcrDependencyError(f"unsupported Office conversion suffix: {suffix or '<none>'}")
    if source.is_symlink() or not source.is_file():
        raise OcrDependencyError("Office conversion input must be a regular non-symlink file")
    if source.stat().st_size > OCR_OFFICE_MAX_INPUT_BYTES:
        raise OcrDependencyError("Office conversion input exceeds configured byte limit")
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if executable is None:
        raise OcrDependencyError("LibreOffice command is not installed")
    with _OFFICE_SEMAPHORE, tempfile.TemporaryDirectory(prefix="ocr-office-") as temp_name:
        root = Path(temp_name)
        input_dir, output_dir, profile = root / "input", root / "output", root / "profile"
        input_dir.mkdir()
        output_dir.mkdir()
        _write_macro_security_profile(profile)
        copied = input_dir / f"input{suffix}"
        shutil.copyfile(source, copied, follow_symlinks=False)
        env = {
            "HOME": str(root),
            "TMPDIR": str(root / "tmp"),
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "SAL_USE_VCLPLUGIN": "svp",
        }
        (root / "tmp").mkdir()
        argv = [
            executable,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(copied),
        ]
        try:
            process = subprocess.Popen(
                argv,
                shell=False,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        except OSError as exc:
            raise OcrDependencyError(f"LibreOffice failed to start: {exc}") from exc
        try:
            try:
                _stdout, stderr = process.communicate(timeout=OCR_OFFICE_TIMEOUT_SEC)
            except subprocess.TimeoutExpired as exc:
                raise OcrDependencyError(
                    f"LibreOffice conversion timed out after {OCR_OFFICE_TIMEOUT_SEC}s"
                ) from exc
            if process.returncode != 0:
                detail = (
                    stderr.decode("utf-8", "replace")[-500:]
                    if isinstance(stderr, bytes)
                    else str(stderr)[-500:]
                )
                raise OcrDependencyError(
                    f"LibreOffice conversion failed ({process.returncode}): {detail}"
                )
            yield _validated_pdf(output_dir, copied.stem)
        finally:
            if isinstance(getattr(process, "pid", None), int):
                _terminate_process_group(process)
