"""Command-line entry point."""

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insidejob",
        description="Alert on new internship, trainee and junior roles.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="fetch sources, alert on new matching jobs")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="print new matches only: no alerts, no state write",
    )
    run.add_argument("--config", type=Path, default=Path("config.yaml"), help="config file")
    run.add_argument("--state", type=Path, default=Path("seen.json"), help="state file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "run":
        # Pipeline lands in PR 4 (#6).
        print(f"run: dry_run={args.dry_run} config={args.config} state={args.state}")
        return 0

    return 1
