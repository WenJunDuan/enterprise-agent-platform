"""Filesystem preprocessing helpers for source documents before Claude invocation."""

from __future__ import annotations

import subprocess
from pathlib import Path


def prepare_text_proxy(source: str, proxy_root: Path) -> tuple[str, str | None]:
    """Create a readable text proxy for PDFs while preserving the canonical source path."""
    source_path = Path(source)
    if source_path.suffix.lower() != ".pdf":
        return source, None

    proxy_root.mkdir(parents=True, exist_ok=True)
    proxy_path = proxy_root / f"{source_path.stem}.txt"
    command = ["pdftotext", str(source_path), str(proxy_path)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "pdftotext failed").strip()
        raise ValueError(f"Failed to prepare readable text proxy for {source}: {message}")

    return source, str(proxy_path)
