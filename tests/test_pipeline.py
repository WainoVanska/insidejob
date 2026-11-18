"""The whole run with a fake HTTP transport: no network."""

from datetime import date, timedelta

import httpx

from insidejob.config import parse_config
from insidejob.pipeline import run
from insidejob.state import State
from tests.helpers import greenhouse_board

DAY1 = date(2026, 11, 18)
DAY2 = DAY1 + timedelta(days=1)

CONFIG = parse_config(
    {
        "filters": {"title": "trainee|intern", "exclude": "senior", "location": "helsinki"},
        "sources": [
            {"company": "Acme", "type": "greenhouse", "board": "acme"},
            {"company": "Beta", "type": "greenhouse", "board": "beta"},
        ],
    }
)


def client_for(boards: dict[str, dict | int]) -> httpx.Client:
    """Serve each board's response; an int means that HTTP error status."""

    def handler(request: httpx.Request) -> httpx.Response:
        board = request.url.path.split("/")[3]
        body = boards[board]
        if isinstance(body, int):
            return httpx.Response(body)
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def go(state: State, boards: dict, today: date = DAY1):
    with client_for(boards) as client:
        return run(CONFIG, state, client, today=today, sleep=lambda _: None)


ACME_DAY1 = greenhouse_board(
    (1, "Summer Trainee", "Helsinki, Finland"),
    (2, "Senior Engineer", "Helsinki, Finland"),
)
BETA = greenhouse_board((10, "Software Intern", "Helsinki"))


def test_first_run_seeds_everything_silently():
    state = State()
    result = go(state, {"acme": ACME_DAY1, "beta": BETA})
    assert result.new_jobs == []
    assert all(r.seeded for r in result.sources)
    assert [j.title for j in result.sources[0].matched] == ["Summer Trainee"]
    assert set(state.boards["greenhouse:acme"]) == {"1", "2"}  # all jobs, not only matches


def test_new_matching_job_is_reported_and_enriched():
    state = State()
    go(state, {"acme": ACME_DAY1, "beta": BETA})
    acme_day2 = greenhouse_board(
        (1, "Summer Trainee", "Helsinki, Finland"),
        (3, "Data Trainee", "Helsinki, Finland"),
        (4, "Senior Trainee Mentor", "Helsinki, Finland"),  # new but excluded
        (5, "Trainee", "Stockholm, Sweden"),  # new but wrong location
    )
    result = go(state, {"acme": acme_day2, "beta": BETA}, DAY2)
    (job,) = result.new_jobs
    assert job.id == "greenhouse:acme:3"
    assert job.workplace == "hybrid"  # from the description, via enrich
    assert "workplace" in job.inferred


def test_failed_source_is_skipped_and_others_still_run():
    state = State()
    go(state, {"acme": ACME_DAY1, "beta": BETA})
    beta_day2 = greenhouse_board((10, "Software Intern", "Helsinki"), (11, "QA Intern", "Helsinki"))
    result = go(state, {"acme": 500, "beta": beta_day2}, DAY2)

    assert [r.source.key for r in result.failed] == ["greenhouse:acme"]
    assert "HTTPStatusError" in result.failed[0].error
    assert [j.id for j in result.new_jobs] == ["greenhouse:beta:11"]
    # The failed board's state is untouched.
    assert state.boards["greenhouse:acme"]["1"]["last_seen"] == DAY1.isoformat()


def test_parse_errors_count_as_failures():
    state = State()
    result = go(state, {"acme": {"jobs": [{"no": "fields"}]}, "beta": BETA})
    assert [r.source.key for r in result.failed] == ["greenhouse:acme"]
    assert not state.knows("greenhouse:acme")


def test_pauses_between_sources_only():
    pauses = []
    with client_for({"acme": ACME_DAY1, "beta": BETA}) as client:
        run(CONFIG, State(), client, today=DAY1, pause=1.5, sleep=pauses.append)
    assert pauses == [1.5]


def test_unconfigured_boards_are_dropped():
    old = {"9": {"first_seen": "2026-01-01", "last_seen": "2026-01-01"}}
    state = State({"greenhouse:old": old})
    go(state, {"acme": ACME_DAY1, "beta": BETA})
    assert set(state.boards) == {"greenhouse:acme", "greenhouse:beta"}
