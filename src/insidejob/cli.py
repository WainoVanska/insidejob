"""Command-line entry point.

Exit codes: 0 ok, 1 at least one source failed (the others still ran and state was
saved), 2 bad config/state or usage.
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from insidejob.config import ConfigError, load_config
from insidejob.format import plain
from insidejob.pipeline import RunResult, make_client, run
from insidejob.state import State, StateError

log = logging.getLogger("insidejob")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insidejob",
        description="Alert on new internship, trainee and junior roles.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="fetch sources, alert on new matching jobs")
    run_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="print matching jobs only: no alerts, no state write",
    )
    run_cmd.add_argument("--config", type=Path, default=Path("config.yaml"), help="config file")
    run_cmd.add_argument("--state", type=Path, default=Path("seen.json"), help="state file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # our own per-source line is enough
    _utf8_stdout()

    if args.command == "run":
        return _run(args)
    return 2


def _run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
        state = State.load(args.state)
    except (ConfigError, StateError) as exc:
        log.error("%s", exc)
        return 2

    today = datetime.now(UTC).date()
    with make_client() as client:
        result = run(config, state, client, today=today)

    if args.dry_run:
        _print_dry_run(result)
    else:
        _print_new(result)
        state.save(args.state)

    if result.failed:
        log.error("%d source(s) failed: %s", len(result.failed), _keys(result.failed))
        return 1
    return 0


def _print_new(result: RunResult) -> None:
    jobs = result.new_jobs
    print(f"{len(jobs)} new job(s)")
    for job in jobs:
        print(plain(job))


def _print_dry_run(result: RunResult) -> None:
    """Show every matching job, so filters can be checked even on a first run."""
    for source in result.sources:
        if not source.matched:
            continue
        print(f"\n== {source.source.company} ({source.source.key})")
        new_ids = {job.id for job in source.new}
        for job in source.matched:
            if source.seeded:
                tag = "seed"
            elif job.id in new_ids:
                tag = "NEW "
            else:
                tag = "seen"
            print(f"[{tag}] {plain(job)}")
    matched = sum(len(s.matched) for s in result.sources)
    print(f"\n{matched} matching, {len(result.new_jobs)} new. Dry run: state not saved.")


def _keys(results) -> str:
    return ", ".join(r.source.key for r in results)


def _utf8_stdout() -> None:
    # Windows consoles default to cp1252, which can't print e.g. "kesä" or "–".
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
