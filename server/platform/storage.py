"""Low-level storage helpers for append-only local backends."""

from __future__ import annotations

import json
import logging
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


def load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into memory."""
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as handle:
        _lock(handle, exclusive=False)
        try:
            lines = handle.readlines()
        finally:
            _unlock(handle)

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSONL at {path}:{line_number}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        records.append(loaded)
    return records


def load_jsonl_records_from_paths(paths: list[Path]) -> list[dict[str, Any]]:
    """Load multiple JSONL files in sorted order."""
    records: list[dict[str, Any]] = []
    for path in sorted(paths):
        records.extend(load_jsonl_records(path))
    return records


def list_jsonl_files(path: Path) -> list[Path]:
    """List JSONL files under a file or shard directory."""
    if path.is_file():
        return [path]
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.jsonl") if item.is_file())


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


def warn_if_store_capacity_exceeded(*, store_name: str, shard_dir: Path, shard_path: Path) -> None:
    """Log soft warnings when append-only shard storage grows beyond configured limits."""
    from server.platform.config import get_app_settings

    settings = get_app_settings()
    shard_size = shard_path.stat().st_size if shard_path.exists() else 0
    shard_count = len(list_jsonl_files(shard_dir))
    if (
        shard_size <= settings.session_store_max_shard_bytes
        and shard_count <= settings.session_store_max_shards
    ):
        return

    logging.getLogger(__name__).warning(
        "store capacity warning",
        extra={
            "store_name": store_name,
            "shard_path": str(shard_path),
            "shard_size_bytes": shard_size,
            "shard_count": shard_count,
            "max_shard_bytes": settings.session_store_max_shard_bytes,
            "max_shards": settings.session_store_max_shards,
        },
    )


def _lock(handle: Any, *, exclusive: bool) -> None:
    if fcntl is None:
        return
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    fcntl.flock(handle.fileno(), mode)


def _unlock(handle: Any) -> None:
    if fcntl is None:
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
