"""CLI entrypoint for local-only administrative workflows."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence, TextIO

from server.rule_init import InitPlan, build_init_plan, initialize_rules


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-cli", description="Enterprise agent platform CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="CLI-only equivalent of /init")
    init_parser.add_argument("domain", nargs="?", default="expense", help="Target domain, default: expense")
    init_parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Explicit source file under knowledge/external. Can be passed multiple times.",
    )
    init_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    project_root: Path | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    root = project_root or Path.cwd()

    if args.command != "init":
        parser.print_help(output_stream)
        return 0

    return _run_init(
        domain=args.domain,
        explicit_sources=args.source,
        assume_yes=args.yes,
        input_stream=input_stream,
        output_stream=output_stream,
        project_root=root,
    )


def _run_init(
    *,
    domain: str,
    explicit_sources: Sequence[str],
    assume_yes: bool,
    input_stream: TextIO,
    output_stream: TextIO,
    project_root: Path,
) -> int:
    plan = build_init_plan(project_root, domain=domain, explicit_sources=explicit_sources)
    _print_plan(plan, output_stream)

    if not assume_yes and not _confirm(input_stream, output_stream):
        output_stream.write("Cancelled /init.\n")
        return 1

    output_stream.write(f"Running /init for domain {domain} ...\n")
    result = initialize_rules(project_root, domain=domain, explicit_sources=explicit_sources)
    output_stream.write(f"Schema written to {result.schema_path.relative_to(project_root)}\n")
    output_stream.write(f"Report written to {result.report_path.relative_to(project_root)}\n")
    output_stream.write(f"Manifest written to {result.manifest_path.relative_to(project_root)}\n")
    output_stream.write(f"Status: {result.status}\n")
    return 0


def _print_plan(plan: InitPlan, output_stream: TextIO) -> None:
    output_stream.write("CLI-only /init preview\n")
    output_stream.write(f"- domain: {plan.domain}\n")
    output_stream.write(f"- external sources: {len(plan.external_sources)}\n")
    output_stream.write(f"- memory sources: {len(plan.memory_sources)}\n")
    output_stream.write(f"- rule targets: {len(plan.rule_targets)}\n")
    output_stream.write(f"- status: {plan.status}\n")
    if plan.warnings:
        output_stream.write("- warnings:\n")
        for warning in plan.warnings:
            output_stream.write(f"  - {warning}\n")


def _confirm(input_stream: TextIO, output_stream: TextIO) -> bool:
    output_stream.write("Proceed with /init? [y/N]: ")
    output_stream.flush()
    answer = input_stream.readline().strip().lower()
    return answer in {"y", "yes"}


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
