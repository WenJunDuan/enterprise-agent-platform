"""Business runtime memory writer."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from threading import Lock
import uuid

from server.config import MemorySettings, load_memory_settings

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


_PATH_LOCKS: dict[str, Lock] = {}
_PATH_LOCKS_GUARD = Lock()


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    source: str
    domain: str
    scenario: str
    input_summary: str
    outcome: str
    rule_ids: tuple[str, ...] = ()
    manual_confirmation: str | None = None
    reusable_judgment: str | None = None
    pending_rule_updates: tuple[str, ...] = ()
    references: tuple[str, ...] = ()


def append_memory_record(
    record: MemoryRecord,
    *,
    now: datetime | None = None,
    settings: MemorySettings | None = None,
) -> Path:
    effective_now = now or datetime.now()
    effective_settings = settings or load_memory_settings()
    daily_path = _daily_memory_path(effective_settings.root_dir, effective_now)
    absolute_daily_path = Path.cwd() / daily_path
    absolute_daily_path.parent.mkdir(parents=True, exist_ok=True)
    with _locked_daily_memory_path(absolute_daily_path):
        document = (
            absolute_daily_path.read_text(encoding="utf-8")
            if absolute_daily_path.exists()
            else _daily_memory_template(effective_now)
        )
        updated_document = _append_record(document, record, effective_now)
        _atomic_write_text(absolute_daily_path, updated_document)
    return daily_path


def _daily_memory_path(root_dir: Path, current_time: datetime) -> Path:
    return (
        root_dir
        / current_time.strftime("%Y")
        / current_time.strftime("%m")
        / f"{current_time.strftime('%Y-%m-%d')}.md"
    )


def _daily_memory_template(current_time: datetime) -> str:
    date_string = current_time.strftime("%Y-%m-%d")
    return (
        f"# 业务运行记忆 - {date_string}\n\n"
        "## 当日概览\n\n"
        f"- 日期：{date_string}\n"
        "- 记录来源：Claude 在业务运行过程中持续沉淀\n"
        "- 记录目标：沉淀可复用的业务判断、人工确认和规则线索\n\n"
        "## 业务事件记录\n\n"
        "## 规则命中与处理\n\n"
        "## 人工确认与例外\n\n"
        "## 可沉淀业务记忆\n\n"
        "## 待固化规则\n\n"
        "## 关联资料\n"
    )


def _render_event_block(record: MemoryRecord, current_time: datetime) -> str:
    lines = [
        f"### {current_time.strftime('%H:%M:%S')} | {record.domain} | {record.scenario}",
        f"- 来源：{record.source}",
        f"- 输入摘要：{record.input_summary}",
        f"- 处理结果：{record.outcome}",
    ]
    if record.rule_ids:
        lines.append("- 命中规则：" + ", ".join(f"`{rule_id}`" for rule_id in record.rule_ids))
    if record.manual_confirmation:
        lines.append(f"- 人工确认：{record.manual_confirmation}")
    if record.reusable_judgment:
        lines.append(f"- 可复用判断：{record.reusable_judgment}")
    if record.pending_rule_updates:
        lines.append("- 待固化规则：" + "；".join(record.pending_rule_updates))
    if record.references:
        lines.append("- 关联资料：" + "；".join(record.references))
    return "\n".join(lines)


def _render_rule_summary(record: MemoryRecord, current_time: datetime) -> str | None:
    if not record.rule_ids:
        return None
    return (
        f"- {current_time.strftime('%H:%M:%S')} | {record.domain} | "
        f"{', '.join(f'`{rule_id}`' for rule_id in record.rule_ids)} | {record.outcome}"
    )


def _render_confirmation_summary(record: MemoryRecord, current_time: datetime) -> str | None:
    if not record.manual_confirmation:
        return None
    return f"- {current_time.strftime('%H:%M:%S')} | {record.manual_confirmation}"


def _append_under_section(document: str, section_name: str, block: str) -> str:
    marker = f"## {section_name}\n"
    normalized_document = document if document.endswith("\n") else f"{document}\n"
    if marker not in normalized_document:
        return normalized_document + f"\n{marker}\n{block.rstrip()}\n"

    prefix, suffix = normalized_document.split(marker, 1)
    next_marker = "\n## "
    if next_marker in suffix:
        section_body, tail = suffix.split(next_marker, 1)
        updated_body = _merge_section_body(section_body, block)
        return f"{prefix}{marker}{updated_body}\n## {tail}"

    updated_body = _merge_section_body(suffix, block)
    return f"{prefix}{marker}{updated_body}"


def _merge_section_body(existing_body: str, block: str) -> str:
    trimmed_body = existing_body.strip()
    trimmed_block = block.rstrip()
    if not trimmed_body:
        return f"{trimmed_block}\n\n"
    return f"{trimmed_body}\n\n{trimmed_block}\n\n"


def _append_record(document: str, record: MemoryRecord, current_time: datetime) -> str:
    updated_document = _append_under_section(
        document,
        "业务事件记录",
        _render_event_block(record, current_time),
    )

    rule_summary = _render_rule_summary(record, current_time)
    if rule_summary:
        updated_document = _append_under_section(updated_document, "规则命中与处理", rule_summary)

    confirmation_summary = _render_confirmation_summary(record, current_time)
    if confirmation_summary:
        updated_document = _append_under_section(updated_document, "人工确认与例外", confirmation_summary)

    if record.reusable_judgment:
        updated_document = _append_under_section(
            updated_document,
            "可沉淀业务记忆",
            f"- {current_time.strftime('%H:%M:%S')} | {record.reusable_judgment}",
        )

    if record.pending_rule_updates:
        pending_block = "\n".join(
            f"- {current_time.strftime('%H:%M:%S')} | {item}" for item in record.pending_rule_updates
        )
        updated_document = _append_under_section(updated_document, "待固化规则", pending_block)

    if record.references:
        reference_block = "\n".join(
            f"- {current_time.strftime('%H:%M:%S')} | {item}" for item in record.references
        )
        updated_document = _append_under_section(updated_document, "关联资料", reference_block)

    return updated_document


def _atomic_write_text(path: Path, content: str) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)


@contextmanager
def _locked_daily_memory_path(path: Path):
    thread_lock = _get_path_lock(path)
    with thread_lock:
        lock_path = path.with_name(f".{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _get_path_lock(path: Path) -> Lock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _PATH_LOCKS[key] = lock
        return lock
