"""CLI end to end, with the HTTP client swapped for a fake: no network."""

import json

import httpx
import pytest

from insidejob import cli
from tests.helpers import greenhouse_board

CONFIG = """\
filters:
  title: 'trainee'
sources:
  - { company: Acme, type: greenhouse, board: acme }
"""


@pytest.fixture
def files(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return config, tmp_path / "seen.json"


@pytest.fixture
def board(monkeypatch):
    """Serve whatever response is in `current`; an int is an HTTP error status."""
    current = {"body": greenhouse_board((1, "Summer Trainee", "Helsinki"))}

    def handler(request):
        body = current["body"]
        if isinstance(body, int):
            return httpx.Response(body)
        return httpx.Response(200, json=body)

    monkeypatch.setattr(
        cli, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return current


def run_cli(config, state, *extra):
    return cli.main(["run", "--config", str(config), "--state", str(state), *extra])


def test_dry_run_prints_matches_and_saves_nothing(files, board, capsys):
    config, state = files
    assert run_cli(config, state, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "[seed] Acme – Summer Trainee" in out
    assert not state.exists()


def test_real_run_seeds_then_reports_new(files, board, capsys):
    config, state = files
    assert run_cli(config, state) == 0
    assert "0 new job(s)" in capsys.readouterr().out
    assert json.loads(state.read_text(encoding="utf-8"))["greenhouse:acme"]

    board["body"] = greenhouse_board(
        (1, "Summer Trainee", "Helsinki"),
        (2, "Data Trainee", "Espoo"),
    )
    assert run_cli(config, state) == 0
    out = capsys.readouterr().out
    assert "1 new job(s)" in out
    assert "Acme – Data Trainee" in out


def test_failed_source_exits_1_but_saves_state(files, board):
    config, state = files
    board["body"] = 503
    assert run_cli(config, state) == 1
    assert state.exists()


def test_bad_config_exits_2(tmp_path, board):
    config = tmp_path / "config.yaml"
    config.write_text("filters: {}\nsources: []\n", encoding="utf-8")
    assert run_cli(config, tmp_path / "seen.json") == 2


def test_missing_command_is_an_error():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
