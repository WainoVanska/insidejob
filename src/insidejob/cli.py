"""Command-line entry point.

    insidejob run [--dry-run]        hourly: alert on new matching jobs, save state
    insidejob top [--count N]        on demand: send the N best matching jobs right now
    insidejob check                  validate config.yaml and preview matches; never sends

Exit codes: 0 ok; 1 a source failed (the others still ran and state was saved) or the
alert could not be sent (state not saved, so the jobs are retried next run); 2 bad
config, state, usage or a missing DISCORD_WEBHOOK_URL. `check` exits 1 on any problem.
The first run that seeds an empty state also sends a welcome message; if that fails,
state is still saved and the exit code is 1.
"""

import argparse
import logging
import os
import re
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from insidejob.config import ConfigError, load_config
from insidejob.format import match_dot, plain, plural, reason_line, score_text
from insidejob.models import Job
from insidejob.notify.discord import DiscordNotifier, top_header, welcome_header
from insidejob.pipeline import RunResult, make_client, run
from insidejob.rank import RankConfig, RankedJob, rank_jobs
from insidejob.state import State, StateError

log = logging.getLogger("insidejob")

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"
FRESH_DAYS = 7  # `top` marks jobs first seen within this many days with 🆕
WELCOME_TOP = 3  # jobs shown in the welcome message on the first run
CHECK_TOP = 5  # jobs shown by `check`


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
    top_cmd = commands.add_parser(
        "top", help="send the best-matching current jobs (reads state, never writes it)"
    )
    top_cmd.add_argument(
        "--count", type=_positive_int, default=10, help="how many jobs to send (default 10)"
    )
    top_cmd.add_argument("--dry-run", action="store_true", help="print only: no alert")
    check_cmd = commands.add_parser(
        "check", help="check config.yaml: list companies, preview matches, send nothing"
    )

    for cmd in (run_cmd, top_cmd, check_cmd):
        cmd.add_argument("--config", type=Path, default=Path("config.yaml"), help="config file")
    for cmd in (run_cmd, top_cmd):
        cmd.add_argument("--state", type=Path, default=Path("seen.json"), help="state file")
    return parser


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a whole number of at least 1, not {text!r}")
    return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # our own per-source line is enough
    _utf8_stdout()

    if args.command == "run":
        return _run(args)
    if args.command == "top":
        return _top(args)
    if args.command == "check":
        return _check(args)
    return 2


def _run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
        state = State.load(args.state)
    except (ConfigError, StateError) as exc:
        log.error("%s", exc)
        return 2

    load_dotenv(Path(".env"))
    webhook = os.environ.get(WEBHOOK_ENV, "").strip()
    if not args.dry_run and not webhook:
        log.error("%s is not set: put it in .env, or use --dry-run", WEBHOOK_ENV)
        return 2

    today = datetime.now(UTC).date()
    first_run = not state.boards  # nothing seen yet: this run seeds every board
    welcome_failed = False
    with make_client() as client:
        result = run(config, state, client, today=today)

        if args.dry_run:
            _print_dry_run(result, config.rank, today)
        else:
            new = [replace(i, fresh=True) for i in rank_jobs(result.new_jobs, config.rank, today)]
            _print_new(new)
            if first_run and len(result.failed) < len(result.sources):
                # Say hello, so a new user sees it works without waiting for a new job.
                # State is saved even if this fails: the seeding itself went fine.
                matched = _matched(result)
                best = rank_jobs(matched, config.rank, today)[:WELCOME_TOP]
                header = welcome_header(len(config.sources), len(matched), len(best))
                try:
                    DiscordNotifier(webhook, client).send(best, header)
                except Exception as exc:
                    log.error("sending the welcome message failed: %s", _redact(exc))
                    welcome_failed = True
            elif new:
                try:
                    DiscordNotifier(webhook, client).send(new)
                except Exception as exc:
                    # Don't save: the same jobs are still "new" next run and get retried.
                    log.error("sending the alert failed, state not saved: %s", _redact(exc))
                    return 1
            state.save(args.state)

    if welcome_failed:
        return 1
    if result.failed:
        log.error("%d source(s) failed: %s", len(result.failed), _keys(result.failed))
        return 1
    return 0


def _top(args: argparse.Namespace) -> int:
    """Send the best `--count` jobs matching right now, whether new or not.

    State is read (to mark jobs first seen in the last FRESH_DAYS with 🆕) but never saved,
    so this can run any time without affecting the hourly alerts.
    """
    try:
        config = load_config(args.config)
        state = State.load(args.state)
    except (ConfigError, StateError) as exc:
        log.error("%s", exc)
        return 2

    load_dotenv(Path(".env"))
    webhook = os.environ.get(WEBHOOK_ENV, "").strip()
    if not args.dry_run and not webhook:
        log.error("%s is not set: put it in .env, or use --dry-run", WEBHOOK_ENV)
        return 2

    today = datetime.now(UTC).date()
    with make_client() as client:
        result = run(config, state, client, today=today)  # updates state in memory only
        items = top_jobs(result, state, config.rank, today, args.count)

        print(f"top {len(items)} job(s)")
        for item in items:
            print(("🆕 " if item.fresh else "") + plain(item.job, item.rank))
        if items and not args.dry_run:
            try:
                DiscordNotifier(webhook, client).send(items, top_header(len(items)))
            except Exception as exc:
                log.error("sending the top jobs failed: %s", _redact(exc))
                return 1

    if result.failed:
        log.error("%d source(s) failed: %s", len(result.failed), _keys(result.failed))
        return 1
    return 0


def _check(args: argparse.Namespace) -> int:
    """Validate the config, then fetch every board (with an empty in-memory state) and
    show what would match. Prints to the terminal and, in GitHub Actions, writes the same
    report to the job summary with error annotations. Never sends, never writes state."""
    summary: list[str] = []
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        log.error("%s", exc)
        _annotate(f"{args.config}: {exc}", "Config problem")
        summary.append(f"## ❌ {args.config} has a problem\n\n{exc}\n\nFix it and push again.")
        _write_summary(summary)
        return 1

    names = ", ".join(s.company for s in config.sources)
    print(f"Config OK. Watching {plural(len(config.sources), 'company', 'companies')}: {names}\n")

    today = datetime.now(UTC).date()
    # The pipeline's per-source lines talk about seeding state, which `check` never
    # keeps: show our own per-company line instead (errors still come through).
    logging.getLogger("insidejob.pipeline").setLevel(logging.WARNING)
    with make_client() as client:
        result = run(config, State(), client, today=today)
    matched = _matched(result)
    best = rank_jobs(matched, config.rank, today)[:CHECK_TOP]

    summary += [
        f"## ✅ Watching {plural(len(config.sources), 'company', 'companies')}"
        f" · {plural(len(matched), 'matching job')} now",
        "",
        "| Company | Jobs open | Matching |",
        "|---|---:|---:|",
    ]
    for r in result.sources:
        if r.error:
            message = (
                f"{r.source.company} ({r.source.key}): couldn't read its job board, "
                f"check the link. {r.error}"
            )
            log.error("%s", message)
            _annotate(message, "Company not reachable")
            summary.append(f"| ❌ {_md(r.source.company)} | failed | |")
        else:
            print(f"  {r.source.company}: {r.fetched} jobs open, {len(r.matched)} matching")
            summary.append(f"| {_md(r.source.company)} | {r.fetched} | {len(r.matched)} |")

    print(f"\nTop {len(best)} of {len(matched)} matching job(s):")
    summary += ["", f"### Top {len(best)} matches", ""]
    for i, item in enumerate(best, 1):
        job, rank = item.job, item.rank
        print(plain(job, rank))
        summary.append(
            f"{i}. {match_dot(rank)} **{score_text(rank)}** {_md(job.company)}: "
            f"[{_md(job.title)}]({job.url})  \n   {_md(reason_line(rank, ''))}"
        )
    if not best:
        summary.append("No matching jobs open right now. New ones will still be alerted.")
    summary += ["", "_Nothing was sent: this check never posts to Discord._"]
    _write_summary(summary)

    if result.failed:
        log.error("%d company board(s) failed: %s", len(result.failed), _keys(result.failed))
        return 1
    return 0


def _write_summary(lines: list[str]) -> None:
    """Append markdown to the GitHub Actions job summary, when running there."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def _annotate(message: str, title: str) -> None:
    """A GitHub Actions error annotation (shown on the run page); nothing when local."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title={title}::{escaped}")


def _md(text: str) -> str:
    """Text safe inside a markdown table cell or link label."""
    return re.sub(r"([\\|\[\]*_`<>])", r"\\\1", text)


def _matched(result: RunResult) -> list[Job]:
    return [job for s in result.sources for job in s.matched]


def top_jobs(
    result: RunResult, state: State, rank_config: RankConfig, today: date, count: int
) -> list[RankedJob]:
    """The `count` best matching jobs. Fresh = first seen within FRESH_DAYS, on a board
    that already had history (a board seen for the first time would make everything 🆕)."""
    known = {s.source.key for s in result.sources if not s.seeded}
    since = today - timedelta(days=FRESH_DAYS - 1)
    matched = [job for s in result.sources for job in s.matched]
    best = rank_jobs(matched, rank_config, today)[:count]

    def fresh(job) -> bool:
        first = state.first_seen(job)
        return job.source in known and first is not None and first >= since

    return [replace(item, fresh=fresh(item.job)) for item in best]


def _print_new(items: list[RankedJob]) -> None:
    print(f"{len(items)} new job(s)")
    for item in items:
        print(plain(item.job, item.rank))


def _print_dry_run(result: RunResult, rank_config: RankConfig, today: date) -> None:
    """Show every matching job, ranked, so filters and weights can be checked on a first run."""
    seeded = {s.source.key for s in result.sources if s.seeded}
    new_ids = {job.id for job in result.new_jobs}
    matched = [job for s in result.sources for job in s.matched]
    for item in rank_jobs(matched, rank_config, today):
        job = item.job
        if job.source in seeded:
            tag = "seed"
        elif job.id in new_ids:
            tag = "NEW "
        else:
            tag = "seen"
        print(f"\n[{tag}] {plain(job, item.rank)}")
    print(f"\n{len(matched)} matching, {len(new_ids)} new. Dry run: state not saved.")


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
