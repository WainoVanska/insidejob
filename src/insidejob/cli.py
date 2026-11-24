"""Command-line entry point.

Exit codes: 0 ok; 1 a source failed (the others still ran and state was saved) or the
alert could not be sent (state not saved, so the jobs are retried next run); 2 bad
config, state, usage or a missing DISCORD_WEBHOOK_URL.
"""

import argparse
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from insidejob.config import ConfigError, load_config
from insidejob.format import plain
from insidejob.health import Health, HealthError, health_path
from insidejob.notify.discord import DiscordNotifier, build_heartbeat
from insidejob.pipeline import RunResult, make_client, run
from insidejob.state import State, StateError

log = logging.getLogger("insidejob")

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


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
    run_cmd.add_argument(
        "--heartbeat",
        action="store_true",
        help="also send a short 'still alive' summary to Discord (the weekly check-in)",
    )
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
        health = Health.load(health_path(args.state))
    except (ConfigError, StateError, HealthError) as exc:
        log.error("%s", exc)
        return 2

    load_dotenv(Path(".env"))
    webhook = os.environ.get(WEBHOOK_ENV, "").strip()
    if not args.dry_run and not webhook:
        log.error("%s is not set: put it in .env, or use --dry-run", WEBHOOK_ENV)
        return 2

    today = datetime.now(UTC).date()
    with make_client() as client:
        result = run(config, state, client, today=today)

        if args.dry_run:
            _print_dry_run(result)
        else:
            _print_new(result)
            if result.new_jobs:
                try:
                    DiscordNotifier(webhook, client).send(result.new_jobs)
                except Exception as exc:
                    # Don't save: the same jobs are still "new" next run and get retried.
                    log.error("sending the alert failed, state not saved: %s", _redact(exc))
                    return 1
            state.save(args.state)
            _save_health(health, result, config, today, health_path(args.state))
            if args.heartbeat:
                try:
                    DiscordNotifier(webhook, client).send_text(_heartbeat(result, health))
                except Exception as exc:
                    log.error("sending the heartbeat failed: %s", _redact(exc))
                    return 1

    if result.failed:
        log.error("%d source(s) failed: %s", len(result.failed), _keys(result.failed))
        return 1
    return 0


def _save_health(health: Health, result: RunResult, config, today, path: Path) -> None:
    for source in result.sources:
        health.record(source.source.key, ok=not source.error, today=today)
    health.retain(s.key for s in config.sources)
    health.save(path)


def _heartbeat(result: RunResult, health: Health) -> str:
    failing = [
        (r.source.company, r.source.key, health.failing_since(r.source.key)) for r in result.failed
    ]
    matching = sum(len(s.matched) for s in result.sources)
    return build_heartbeat(len(result.sources), matching, failing)


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


def load_dotenv(path: Path) -> None:
    """Minimal .env support (KEY=VALUE lines) for local runs; real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _redact(exc: Exception) -> str:
    """Error text without the webhook URL: the URL itself is the secret."""
    return re.sub(r"https://\S*discord\S*/api/webhooks/\S+", "<webhook>", str(exc))


def _keys(results) -> str:
    return ", ".join(r.source.key for r in results)


def _utf8_stdout() -> None:
    # Windows consoles default to cp1252, which can't print e.g. "kesä" or "–".
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
