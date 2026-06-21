"""Domain-driven prompt assembly: build one self-contained lean prompt per domain.

Generalizes the audit inline-prompt recipe (instructions + case materials + local
rules [+ optional OCR pre-read]) so every business domain assembles the *same shape*
of lean prompt from a small ``DomainProfile`` registry entry, instead of each domain
hand-rolling its own builder. This is the assembler half of the "域驱动上下文装配"
sprint; domain-specific ``DomainProfile`` instances live in their own domain modules
(e.g. ``server/audit/runner.py``) because ``common/`` must not import feature domains.

P1 scope: pure refactor — byte-identical to the previous audit builder (see
``tests/test_domain_profile.py`` golden snapshots). No behavior change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from server.platform import paths

# 三个 section 标题是跨域共享的 prompt 骨架；具体指令/规则/兜底文案由 DomainProfile 提供。
CASE_SECTION_HEADER = "=== 本案材料 ==="
RULES_SECTION_HEADER = "=== 本地规则（唯一依据）==="
OCR_SECTION_HEADER = "=== 附件 OCR/直读底稿（确定性预处理，优先用此文本，无需再 Read）==="
ATTACHMENT_LISTING_HEADER = "### 附件文件清单（如需查看原件可用 Read 读取）"


@dataclass(frozen=True)
class DomainProfile:
    """Everything the assembler needs to compose a domain's lean prompt.

    Attributes:
        domain: Business domain key (``expense`` / ``tender`` / …); registry identity.
        instructions: The system-style instruction block prepended to the prompt.
        rules_dir: Directory of local rule ``*.json`` files concatenated as the
            "本地规则" section (the sole authority the agent may cite).
        request_file: Filename of the case request JSON inside the case directory.
        case_missing_fallback: Text used when no case materials are found.
        rules_missing_fallback: Text used when no local rules are found.
        result_contract: Result schema name this domain's output must satisfy
            (documentary in P1; consumed by the contract layer downstream).
    """

    domain: str
    instructions: str
    rules_dir: Path
    request_file: str
    case_missing_fallback: str
    rules_missing_fallback: str
    result_contract: str


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def resolve_case_dir(directory_path: str, project_root: Path) -> Path | None:
    """Resolve a case directory, rejecting any path that escapes ``project_root``.

    Args:
        directory_path: Absolute or project-relative path to the case directory.
        project_root: The boundary; resolved paths outside it are refused.

    Returns:
        The resolved directory ``Path``, or ``None`` when the path escapes the
        project root (traversal guard) or does not point to an existing directory.
    """
    candidate = Path(directory_path)
    resolved = (candidate if candidate.is_absolute() else project_root / candidate).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return None
    return resolved if resolved.is_dir() else None


def load_rules(rules_dir: Path) -> str:
    """Concatenate every rule ``*.json`` file in ``rules_dir`` with filename headers.

    Returns an empty string when the directory is missing or has no JSON files;
    callers substitute a domain-specific fallback message.
    """
    if not rules_dir.is_dir():
        return ""
    blocks: list[str] = []
    for path in sorted(rules_dir.glob("*.json")):
        text = _read_text(path)
        if text is not None:
            blocks.append(f"### {path.name}\n{text}")
    return "\n\n".join(blocks)


def load_case_block(directory_path: str, project_root: Path, request_file: str) -> str:
    """Read the case request JSON inline and list attachments by name.

    Returns an empty string when the directory cannot be resolved or is empty;
    callers substitute a domain-specific fallback message.
    """
    case_dir = resolve_case_dir(directory_path, project_root)
    if case_dir is None:
        return ""
    blocks: list[str] = []
    request_text = _read_text(case_dir / request_file)
    if request_text is not None:
        blocks.append(f"### {request_file}\n{request_text}")
    attachments = [
        p.name for p in sorted(case_dir.iterdir()) if p.is_file() and p.name != request_file
    ]
    if attachments:
        listing = "\n".join(f"- {directory_path}/{name}" for name in attachments)
        blocks.append(f"{ATTACHMENT_LISTING_HEADER}\n{listing}")
    return "\n\n".join(blocks)


def assemble_domain_prompt(
    profile: DomainProfile,
    directory_path: str,
    *,
    project_root: Path | None = None,
    ocr_block: str | None = None,
) -> str:
    """Compose a self-contained lean prompt: instructions + case materials + rules.

    The single entry point every inline worker uses, so all domains emit the same
    prompt shape and run with ``setting_sources=[]`` (no project CLAUDE.md载入).

    Args:
        profile: The domain's registry entry (instructions / rules / fallbacks).
        directory_path: Case directory (absolute or project-relative).
        project_root: Traversal boundary; defaults to ``paths.PROJECT_ROOT``.
        ocr_block: Optional deterministic OCR/direct-read pre-read of attachments;
            when present it is injected so the agent need not Read the files.

    Returns:
        A self-contained prompt string.
    """
    root = project_root if project_root is not None else paths.PROJECT_ROOT
    case_block = load_case_block(directory_path, root, profile.request_file) or profile.case_missing_fallback
    rules_block = load_rules(profile.rules_dir) or profile.rules_missing_fallback
    ocr_section = f"\n\n{OCR_SECTION_HEADER}\n{ocr_block}" if ocr_block else ""
    return (
        f"{profile.instructions}\n"
        f"{CASE_SECTION_HEADER}\n{case_block}{ocr_section}\n\n"
        f"{RULES_SECTION_HEADER}\n{rules_block}\n"
    )
