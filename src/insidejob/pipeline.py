"""One run: fetch -> parse -> diff against state -> filter -> enrich, per source.

The state diff runs on *all* parsed jobs (see `state.py`), and only the matching new
ones are enriched and reported. A failing source is logged and skipped: its state is
left untouched, and the other sources still run.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import httpx

from insidejob import __version__
from insidejob.adapters import ADAPTERS
from insidejob.config import Config, Source
from insidejob.enrich import enrich
from insidejob.filters import matches
from insidejob.models import Job
from insidejob.state import State

log = logging.getLogger(__name__)

USER_AGENT = f"insidejob/{__version__} (+https://github.com/WainoVanska/insidejob)"
TIMEOUT = 20.0
PAUSE_SECONDS = 1.0  # between sources: be polite to the APIs


@dataclass
class SourceResult:
    source: Source
    fetched: int = 0
    matched: list[Job] = field(default_factory=list)
    new: list[Job] = field(default_factory=list)
    seeded: bool = False
    error: str | None = None


@dataclass
class RunResult:
    sources: list[SourceResult]

    @property
    def new_jobs(self) -> list[Job]:
        return [job for result in self.sources for job in result.new]

    @property
    def failed(self) -> list[SourceResult]:
        return [result for result in self.sources if result.error]


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def run(
    config: Config,
    state: State,
    client: httpx.Client,
    *,
    today: date,
    pause: float = PAUSE_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> RunResult:
    results: list[SourceResult] = []
    for i, source in enumerate(config.sources):
        if i:
            sleep(pause)
        results.append(_run_source(source, state, client, today))

    ok = [r.source.key for r in results if not r.error]
    state.prune(ok, today)
    state.retain(s.key for s in config.sources)
    return RunResult(results)


def _run_source(source: Source, state: State, client: httpx.Client, today: date) -> SourceResult:
    result = SourceResult(source)
    adapter = ADAPTERS[source.type]
    try:
        raw = adapter.fetch(client, source.board)
        jobs = adapter.parse(raw, source.board, source.company)
    except Exception as exc:  # one broken source must never stop the others
        result.error = f"{type(exc).__name__}: {exc}"
        log.error("%s failed: %s", source.key, result.error)
        return result

    result.fetched = len(jobs)
    result.seeded = not state.knows(source.key)
    new_ids = state.update(source.key, jobs, today)
    result.matched = [enrich(job) for job in jobs if matches(job, source.filters)]
    result.new = [job for job in result.matched if job.id in new_ids]

    log.info(
        "%s fetched=%d matched=%d new=%d%s",
        source.key,
        result.fetched,
        len(result.matched),
        len(result.new),
        " (first run: seeded silently)" if result.seeded else "",
    )
    return result
