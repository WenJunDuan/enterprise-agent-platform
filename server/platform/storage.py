"""Low-level storage helpers for append-only local backends."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:  # pragma: no cover - Windows fallback is environment-dependent
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback is environment-dependent
    fcntl = None


def append_jsonl_record(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object to a JSONL file with advisory locking when available."""
    serialized = json.dumps(record, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _lock(handle, exclusive=True)
        try:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            _unlock(handle)


def append_json_file(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON object atomically to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def load_json_file(path: Path) -> dict[str, Any] | None:
    """Read one JSON object from disk."""
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return loaded


def describe_storage_target(path: Path) -> dict[str, Any]:
    """Summarize a file or directory storage target for health and readiness checks."""
    if path.is_dir():
        files = [item for item in path.rglob("*") if item.is_file()]
        writable_target = path
        return {
            "path": str(path),
            "exists": True,
            "is_dir": True,
            "file_count": len(files),
            "size_bytes": sum(item.stat().st_size for item in files),
            "writable": os.access(writable_target, os.W_OK),
            "parent_exists": path.parent.exists(),
        }

    writable_target = path if path.exists() else path.parent
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_dir": False,
        "file_count": 1 if path.exists() else 0,
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "writable": os.access(writable_target, os.W_OK),
        "parent_exists": path.parent.exists(),
    }


def _lock(handle: Any, *, exclusive: bool) -> None:
    if fcntl is None:
        return
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    fcntl.flock(handle.fileno(), mode)


def _unlock(handle: Any) -> None:
    if fcntl is None:
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
