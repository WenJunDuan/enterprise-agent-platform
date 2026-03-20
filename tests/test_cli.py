from pathlib import Path
from io import StringIO

from server.cli import run


def _bootstrap_project_root(project_root: Path) -> None:
    (project_root / "knowledge" / "external").mkdir(parents=True)
    (project_root / "docs").mkdir(parents=True)
    (project_root / ".cunzhi-memory").mkdir(parents=True)
    (project_root / "docs" / "expense-control-design.md").write_text("# expense design\n", encoding="utf-8")
    (project_root / "docs" / "architecture-summary.md").write_text("# architecture summary\n", encoding="utf-8")
    (project_root / ".cunzhi-memory" / "preferences.md").write_text("# preferences\n", encoding="utf-8")


def test_init_command_aborts_without_confirmation(tmp_path: Path, monkeypatch) -> None:
    _bootstrap_project_root(tmp_path)
    stdout = StringIO()

    exit_code = run(["init"], input_stream=StringIO("n\n"), output_stream=stdout, project_root=tmp_path)

    assert exit_code == 1
    assert "Cancelled /init." in stdout.getvalue()
    assert not (tmp_path / "knowledge" / "_schema" / "rule.schema.json").exists()


def test_init_command_runs_with_confirmation_and_writes_report(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)
    stdout = StringIO()

    exit_code = run(["init"], input_stream=StringIO("y\n"), output_stream=stdout, project_root=tmp_path)

    assert exit_code == 0
    assert "Running /init for domain expense" in stdout.getvalue()
    assert "knowledge/expense/init-report.md" in stdout.getvalue()
    assert (tmp_path / "knowledge" / "expense" / "init-report.md").is_file()
