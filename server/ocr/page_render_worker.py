"""Isolated PyMuPDF renderer used by :mod:`server.ocr.engine`.

The binary stdout protocol is newline-delimited JSON metadata followed by the
announced number of raw PNG bytes for each page. Errors go to stderr and use a
non-zero exit status so the parent can terminate this process on a hard timeout.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def _write_header(payload: dict[str, object]) -> None:
    sys.stdout.buffer.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _preflight_page_pixels(page, scale: float, max_pixels: int, page_number: int) -> None:
    width = float(page.rect.width)
    height = float(page.rect.height)
    if (
        not math.isfinite(width)
        or not math.isfinite(height)
        or not math.isfinite(scale)
        or width <= 0
        or height <= 0
        or scale <= 0
    ):
        raise RuntimeError(f"PDF page {page_number} has invalid page dimensions")
    pixel_width = math.ceil(width * scale)
    pixel_height = math.ceil(height * scale)
    if pixel_width * pixel_height > max_pixels:
        raise RuntimeError(f"PDF page {page_number} exceeds configured pixel limit")


def render(path: Path, scale: float, max_pixels: int) -> None:
    """Stream bounded PNG page frames to the parent process over stdout."""
    import fitz

    with fitz.open(path) as document:
        _write_header({"type": "meta", "page_count": document.page_count})
        matrix = fitz.Matrix(scale, scale)
        for index in range(document.page_count):
            page = document.load_page(index)
            _preflight_page_pixels(page, scale, max_pixels, index + 1)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixels = pixmap.width * pixmap.height
            if pixels > max_pixels:
                raise RuntimeError(f"PDF page {index + 1} exceeds configured pixel limit")
            content = pixmap.tobytes("png")
            _write_header(
                {"type": "page", "page_number": index + 1, "length": len(content)}
            )
            sys.stdout.buffer.write(content)
            sys.stdout.buffer.flush()


def main() -> int:
    """Run the isolated renderer and expose only a concise stderr diagnostic."""
    try:
        render(Path(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]))
    except Exception as exc:  # child boundary: parent receives a short structured diagnostic
        print(str(exc), file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
