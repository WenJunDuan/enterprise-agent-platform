from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path

import pytest

from server.ocr import OcrDependencyError, office_convert


class _FakeProcess:
    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.returncode = 0
        outdir = Path(argv[argv.index("--outdir") + 1])
        input_path = Path(argv[-1])
        (outdir / f"{input_path.stem}.pdf").write_bytes(b"%PDF-1.7\nvalid")

    def communicate(self, timeout=None):
        return b"", b""

    def wait(self, timeout=None):
        return self.returncode


def test_convert_uses_safe_process_and_ephemeral_macro_profile(tmp_path, monkeypatch):
    source = tmp_path / "input.docx"
    source.write_bytes(b"office")
    seen: list[_FakeProcess] = []
    registries: list[str] = []

    def fake_popen(argv, **kwargs):
        profile_arg = next(arg for arg in argv if arg.startswith("-env:UserInstallation="))
        profile_uri = profile_arg.removeprefix("-env:UserInstallation=")
        profile_path = Path(profile_uri.removeprefix("file://"))
        registries.append(
            (profile_path / "registrymodifications.xcu").read_text(encoding="utf-8")
        )
        process = _FakeProcess(argv, **kwargs)
        seen.append(process)
        return process

    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", fake_popen)

    with office_convert.convert_office_to_pdf(source) as pdf:
        assert pdf.read_bytes().startswith(b"%PDF-")
        assert pdf.parent != source.parent

    process = seen[0]
    assert process.kwargs["shell"] is False
    assert process.kwargs["start_new_session"] is True
    assert "--headless" in process.argv
    profile_arg = next(arg for arg in process.argv if arg.startswith("-env:UserInstallation="))
    assert profile_arg.startswith("-env:UserInstallation=file://")
    registry = registries[0]
    assert 'oor:name="MacroSecurityLevel"' in registry
    assert '<value>3</value>' in registry
    assert 'oor:name="DisableMacrosExecution"' in registry
    assert '<value>true</value>' in registry
    assert "HOME" in process.kwargs["env"]
    assert not pdf.exists()


def test_convert_rejects_bad_pdf_magic(tmp_path, monkeypatch):
    source = tmp_path / "input.ppt"
    source.write_bytes(b"office")

    class BadProcess(_FakeProcess):
        def __init__(self, argv, **kwargs):
            super().__init__(argv, **kwargs)
            outdir = Path(argv[argv.index("--outdir") + 1])
            (outdir / "input.pdf").write_bytes(b"not-pdf")

    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", BadProcess)

    with pytest.raises(OcrDependencyError, match="PDF magic"):
        with office_convert.convert_office_to_pdf(source):
            pass


def test_convert_timeout_terminates_process_group_and_releases_slot(tmp_path, monkeypatch):
    source = tmp_path / "input.odt"
    source.write_bytes(b"office")
    killed: list[tuple[int, int]] = []

    class TimeoutProcess:
        returncode = None
        pid = 4321

        def __init__(self, argv, **kwargs):
            self.argv = argv

        def communicate(self, timeout=None):
            raise office_convert.subprocess.TimeoutExpired(self.argv, timeout)

        def wait(self, timeout=None):
            self.returncode = -15
            return self.returncode

    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", TimeoutProcess)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    with pytest.raises(OcrDependencyError, match="timed out"):
        with office_convert.convert_office_to_pdf(source):
            pass

    assert killed and killed[0][0] == 4321
    assert office_convert._OFFICE_SEMAPHORE.acquire(blocking=False)
    office_convert._OFFICE_SEMAPHORE.release()


def test_convert_rejects_unsupported_suffix(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("x")
    with pytest.raises(OcrDependencyError, match="unsupported"):
        with office_convert.convert_office_to_pdf(source):
            pass


def test_convert_missing_command_is_structured_dependency_error(tmp_path, monkeypatch):
    source = tmp_path / "input.doc"
    source.write_bytes(b"office")
    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: None)

    with pytest.raises(OcrDependencyError, match="not installed"):
        with office_convert.convert_office_to_pdf(source):
            pass


def test_convert_rejects_nonzero_exit(tmp_path, monkeypatch):
    source = tmp_path / "input.ods"
    source.write_bytes(b"office")

    class FailedProcess:
        returncode = 7

        def __init__(self, argv, **kwargs):
            pass

        def communicate(self, timeout=None):
            return b"", b"conversion refused"

    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", FailedProcess)

    with pytest.raises(OcrDependencyError, match=r"conversion failed \(7\)"):
        with office_convert.convert_office_to_pdf(source):
            pass


def test_convert_rejects_missing_output(tmp_path, monkeypatch):
    source = tmp_path / "input.odp"
    source.write_bytes(b"office")

    class NoOutputProcess:
        returncode = 0

        def __init__(self, argv, **kwargs):
            pass

        def communicate(self, timeout=None):
            return b"", b""

    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", NoOutputProcess)

    with pytest.raises(OcrDependencyError, match="no safe PDF"):
        with office_convert.convert_office_to_pdf(source):
            pass


def test_convert_rejects_output_over_byte_limit(tmp_path, monkeypatch):
    source = tmp_path / "input.pptx"
    source.write_bytes(b"office")
    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", _FakeProcess)
    monkeypatch.setattr(office_convert, "OCR_OFFICE_MAX_OUTPUT_BYTES", 5)

    with pytest.raises(OcrDependencyError, match="byte limit"):
        with office_convert.convert_office_to_pdf(source):
            pass


def test_convert_rejects_symlink_output_escape(tmp_path, monkeypatch):
    source = tmp_path / "input.docx"
    source.write_bytes(b"office")
    escaped = tmp_path / "escaped.pdf"
    escaped.write_bytes(b"%PDF-outside")

    class SymlinkProcess:
        returncode = 0

        def __init__(self, argv, **kwargs):
            outdir = Path(argv[argv.index("--outdir") + 1])
            (outdir / "input.pdf").symlink_to(escaped)

        def communicate(self, timeout=None):
            return b"", b""

    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", SymlinkProcess)

    with pytest.raises(OcrDependencyError, match="no safe PDF|regular file"):
        with office_convert.convert_office_to_pdf(source):
            pass


def test_timeout_escalates_term_to_kill_and_waits(tmp_path, monkeypatch):
    source = tmp_path / "input.odt"
    source.write_bytes(b"office")
    signals = []
    waits = []

    class StuckProcess:
        returncode = None
        pid = 9876

        def __init__(self, argv, **kwargs):
            self.argv = argv

        def communicate(self, timeout=None):
            raise office_convert.subprocess.TimeoutExpired(self.argv, timeout)

        def wait(self, timeout=None):
            waits.append(timeout)
            if len(waits) == 1:
                raise office_convert.subprocess.TimeoutExpired(self.argv, timeout)
            self.returncode = -9
            return self.returncode

    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", StuckProcess)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    with pytest.raises(OcrDependencyError, match="timed out"):
        with office_convert.convert_office_to_pdf(source):
            pass

    assert signals == [(9876, signal.SIGTERM), (9876, signal.SIGKILL)]
    assert waits == [5, 5]


def test_office_semaphore_serializes_conversions(tmp_path, monkeypatch):
    sources = [tmp_path / "a.docx", tmp_path / "b.docx"]
    for source in sources:
        source.write_bytes(b"office")
    state = {"active": 0, "max_active": 0}
    guard = threading.Lock()

    class SlowProcess(_FakeProcess):
        def communicate(self, timeout=None):
            with guard:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            time.sleep(0.05)
            with guard:
                state["active"] -= 1
            return b"", b""

    monkeypatch.setattr(office_convert.shutil, "which", lambda _name: "/usr/bin/soffice")
    monkeypatch.setattr(office_convert.subprocess, "Popen", SlowProcess)

    def convert(source):
        with office_convert.convert_office_to_pdf(source) as pdf:
            assert pdf.exists()

    threads = [threading.Thread(target=convert, args=(source,)) for source in sources]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert state["max_active"] == 1
