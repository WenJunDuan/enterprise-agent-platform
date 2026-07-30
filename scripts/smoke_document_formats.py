#!/usr/bin/env python3
"""Run the canonical document-format matrix through the real OCR pipeline.

The fixture directory must contain exactly one real sample for every suffix in
``shared/supported-document-formats.json``. Configure the same OCR environment
as the deployed backend before running this script inside the backend image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from contextlib import contextmanager, redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.ocr.formats import ALL_SUPPORTED_SUFFIXES  # noqa: E402
from server.ocr import cache as ocr_cache  # noqa: E402
from server.ocr.pipeline import build_extraction_block, extract_one, is_ocr_text_valid  # noqa: E402
from server.routes.upload_helpers import validate_document_upload  # noqa: E402


class SmokeFailure(RuntimeError):
    """Raised when the deployed document-format contract is not satisfied."""


@contextmanager
def _without_ocr_cache():
    """Hard-disable persistent OCR cache for the duration of a product-image smoke."""
    previous = ocr_cache.OCR_CACHE_ENABLED
    ocr_cache.OCR_CACHE_ENABLED = False
    try:
        yield
    finally:
        ocr_cache.OCR_CACHE_ENABLED = previous


def discover_fixture_paths(fixtures_dir: Path) -> dict[str, Path]:
    """Require one unambiguous, regular fixture for every canonical suffix."""
    if not fixtures_dir.is_dir():
        raise SmokeFailure(f"fixture directory does not exist: {fixtures_dir}")
    candidates = [
        path
        for path in fixtures_dir.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "SOURCES.json"
    ]
    fixtures: dict[str, Path] = {}
    missing: list[str] = []
    duplicates: list[str] = []
    for suffix in sorted(ALL_SUPPORTED_SUFFIXES):
        matches = [path for path in candidates if path.suffix.lower() == suffix]
        if not matches:
            missing.append(suffix)
        elif len(matches) > 1:
            duplicates.append(suffix)
        else:
            fixtures[suffix] = matches[0]
    if missing:
        raise SmokeFailure(f"missing fixtures: {', '.join(missing)}")
    if duplicates:
        raise SmokeFailure(f"duplicate fixtures: {', '.join(duplicates)}")
    return fixtures


def run_smoke(
    fixtures: dict[str, Path],
    *,
    purpose: str = "tender-document-smoke",
    evidence_details: bool = False,
    required_ocr_suffixes: set[str] | None = None,
    expected_engine: str | None = None,
    expected_degraded: bool | None = None,
) -> list[dict]:
    """Validate upload bytes, execute the real route, and require a non-empty draft."""
    required_ocr_suffixes = {
        suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}"
        for suffix in (required_ocr_suffixes or set())
    }
    if required_ocr_suffixes and (expected_engine is None or expected_degraded is None):
        raise SmokeFailure("required OCR suffixes need expected engine and degraded values")
    missing_required = required_ocr_suffixes - set(fixtures)
    if missing_required:
        raise SmokeFailure(f"required OCR fixtures missing: {', '.join(sorted(missing_required))}")

    reports: list[dict] = []
    with _without_ocr_cache():
        for suffix, path in sorted(fixtures.items()):
            fixture_bytes = path.read_bytes()
            validate_document_upload(path.name, fixture_bytes)
            captured_stdout = StringIO()
            completed_units: list[dict] = []
            with redirect_stdout(captured_stdout):
                result = extract_one(
                    path,
                    purpose=purpose,
                    on_unit_complete=completed_units.append,
                )
            block = build_extraction_block([result])
            failed = (
                result.get("kind") in {"error", "manual"}
                or result.get("route") == "manual"
                or bool(result.get("error"))
                or not is_ocr_text_valid(block)
            )
            if failed:
                detail = result.get("error") or "manual route or empty extraction draft"
                raise SmokeFailure(f"{path.name}: {detail}")
            if not completed_units:
                raise SmokeFailure(f"{path.name}: pipeline emitted no completion evidence")
            if any(unit.get("from_cache") is not False for unit in completed_units):
                raise SmokeFailure(f"{path.name}: cache hit or invalid cache evidence detected")

            report = {
                "suffix": suffix,
                "route": result.get("route"),
                "kind": result.get("kind"),
                "status": "ok",
                "from_cache": False,
            }
            if suffix in required_ocr_suffixes:
                actual_engine = result.get("engine")
                actual_degraded = result.get("degraded") is True
                if result.get("route") not in {"ocr", "convert"}:
                    raise SmokeFailure(
                        f"{suffix}: required OCR route was {result.get('route')!r}"
                    )
                if actual_engine != expected_engine:
                    raise SmokeFailure(
                        f"{suffix}: engine {actual_engine!r} != expected {expected_engine!r}"
                    )
                if actual_degraded is not expected_degraded:
                    raise SmokeFailure(
                        f"{suffix}: degraded {actual_degraded!r} != expected {expected_degraded!r}"
                    )
                report["ocr_expectation"] = "matched"
            if evidence_details:
                report.update(
                    {
                        "upload_validation": "ok",
                        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
                        "draft_chars": len(block.strip()),
                        "engine": result.get("engine"),
                        "degraded": result.get("degraded") is True,
                        "clarity": result.get("clarity"),
                        "diagnostics": captured_stdout.getvalue().strip() or None,
                    }
                )
            reports.append(report)
    return reports


def _execution_context() -> dict:
    """Describe the exact host and OCR runtime that produced smoke evidence."""
    system = platform.system()
    architecture = platform.machine()
    tesseract = shutil.which("tesseract")
    version = None
    languages: list[str] = []
    if tesseract:
        version = subprocess.run(
            [tesseract, "--version"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.splitlines()[0]
        language_output = subprocess.run(
            [tesseract, "--list-langs"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.splitlines()[1:]
        languages = [line.strip() for line in language_output if line.strip()]
    return {
        "executed_at": datetime.now(UTC).isoformat(),
        "execution_scope": f"current runtime: {system} {architecture}",
        "host": {"system": system, "architecture": architecture},
        "ocr": {
            "cloud": os.getenv("OCR_CLOUD", "0"),
            "vl_server_url": os.getenv("OCR_VL_SERVER_URL"),
            "vl_model_name": os.getenv("OCR_VL_MODEL_NAME"),
            "use_paddle_pipeline": os.getenv("OCR_VL_USE_PADDLE_PIPELINE", "0"),
            "fallback": "real Tesseract after intentionally unreachable local VLM endpoint",
        },
        "tesseract": {
            "version": version,
            "languages": languages,
            "tessdata_prefix": os.getenv("TESSDATA_PREFIX"),
            "repository": os.getenv("SMOKE_TESSDATA_REPOSITORY"),
            "commit": os.getenv("SMOKE_TESSDATA_COMMIT"),
            "chi_sim_sha256": os.getenv("SMOKE_TESSDATA_CHI_SIM_SHA256"),
            "eng_sha256": os.getenv("SMOKE_TESSDATA_ENG_SHA256"),
        },
    }


def main() -> int:
    """Run the format matrix and emit machine-gated JSON evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-dir", type=Path, required=True)
    parser.add_argument("--purpose", default="tender-document-smoke")
    parser.add_argument(
        "--expect-engine",
        required=True,
        choices=("openai-compatible-vlm", "tesseract"),
    )
    parser.add_argument("--expect-degraded", required=True, choices=("true", "false"))
    parser.add_argument(
        "--require-ocr-suffix",
        required=True,
        action="append",
        help="canonical OCR suffix that must match engine/degraded; repeat per critical route",
    )
    args = parser.parse_args()
    try:
        fixtures = discover_fixture_paths(args.fixtures_dir.resolve())
        expected_degraded = args.expect_degraded == "true"
        required_ocr_suffixes = set(args.require_ocr_suffix)
        reports = run_smoke(
            fixtures,
            purpose=args.purpose,
            evidence_details=True,
            required_ocr_suffixes=required_ocr_suffixes,
            expected_engine=args.expect_engine,
            expected_degraded=expected_degraded,
        )
    except (OSError, SmokeFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    payload = {
        "status": "ok",
        **_execution_context(),
        "expectation": {
            "engine": args.expect_engine,
            "degraded": expected_degraded,
            "required_ocr_suffixes": sorted(required_ocr_suffixes),
            "cache_enabled": False,
        },
        "formats": reports,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
