import json
from datetime import date, timedelta

import pytest

from insidejob.state import PRUNE_AFTER, State, StateError
from tests.helpers import make_job

DAY1 = date(2026, 11, 18)
DAY2 = DAY1 + timedelta(days=1)
SRC = "greenhouse:acme"


def test_first_sight_of_a_board_seeds_silently():
    state = State()
    assert state.update(SRC, [make_job("1"), make_job("2")], DAY1) == set()
    assert set(state.boards[SRC]) == {"1", "2"}


def test_unseen_job_on_known_board_is_new():
    state = State()
    state.update(SRC, [make_job("1")], DAY1)
    assert state.update(SRC, [make_job("1"), make_job("2")], DAY2) == {f"{SRC}:2"}


def test_known_job_only_updates_last_seen():
    state = State()
    state.update(SRC, [make_job("1")], DAY1)
    assert state.update(SRC, [make_job("1")], DAY2) == set()
    assert state.boards[SRC]["1"] == {"first_seen": "2026-11-18", "last_seen": "2026-11-19"}


def test_board_with_no_jobs_is_still_known():
    state = State()
    state.update(SRC, [], DAY1)
    assert state.update(SRC, [make_job("1")], DAY2) == {f"{SRC}:1"}


def test_prune_forgets_long_gone_jobs():
    state = State()
    state.update(SRC, [make_job("old"), make_job("live")], DAY1)
    later = DAY1 + PRUNE_AFTER + timedelta(days=1)
    state.update(SRC, [make_job("live")], later)
    assert state.prune([SRC], later) == 1
    assert set(state.boards[SRC]) == {"live"}


def test_prune_keeps_recent_jobs():
    state = State()
    state.update(SRC, [make_job("1")], DAY1)
    assert state.prune([SRC], DAY1 + PRUNE_AFTER) == 0


def test_prune_skips_sources_not_passed():
    # A board that failed this run keeps its history, or it would look new on recovery.
    state = State()
    state.update(SRC, [make_job("1")], DAY1)
    assert state.prune([], DAY1 + timedelta(days=365)) == 0
    assert "1" in state.boards[SRC]


def test_prune_keeps_empty_board():
    state = State()
    state.update(SRC, [make_job("1")], DAY1)
    state.prune([SRC], DAY1 + timedelta(days=365))
    assert state.knows(SRC)


def test_retain_drops_unconfigured_boards():
    state = State()
    state.update(SRC, [], DAY1)
    state.update("greenhouse:gone", [], DAY1)
    state.retain([SRC])
    assert list(state.boards) == [SRC]


def test_round_trip(tmp_path):
    path = tmp_path / "state" / "seen.json"
    state = State()
    state.update(SRC, [make_job("1")], DAY1)
    state.save(path)
    assert State.load(path).boards == state.boards
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_save_is_sorted_and_stable(tmp_path):
    path = tmp_path / "seen.json"
    state = State()
    state.update(SRC, [make_job("2"), make_job("1")], DAY1)
    state.save(path)
    assert list(json.loads(path.read_text(encoding="utf-8"))[SRC]) == ["1", "2"]


def test_missing_file_is_a_fresh_start(tmp_path):
    assert State.load(tmp_path / "nope.json").boards == {}


def test_empty_file_is_a_fresh_start(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("", encoding="utf-8")
    assert State.load(path).boards == {}


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '{"greenhouse:a": 3}'])
def test_corrupt_file_is_an_error(tmp_path, text):
    path = tmp_path / "seen.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(StateError):
        State.load(path)


def test_first_seen():
    state = State(
        {"greenhouse:acme": {"1": {"first_seen": "2026-11-01", "last_seen": "2026-11-18"}}}
    )
    assert state.first_seen(make_job("1")) == date(2026, 11, 1)
    assert state.first_seen(make_job("2")) is None
    assert state.first_seen(make_job("1", source="ashby:other")) is None
