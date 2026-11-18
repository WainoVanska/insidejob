"""CLI end to end, with the HTTP client swapped for a fake: no network.

Tests run in a temp directory so a real `.env` in the repo can never be picked up.
"""

import json

import httpx
import pytest

from insidejob import cli
from tests.helpers import greenhouse_board

WEBHOOK = "https://discord.test/api/webhooks/1/secret-token"
CONFIG = """\
filters:
  title: 'trainee'
sources:
  - { company: Acme, type: greenhouse, board: acme }
"""


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(cli.WEBHOOK_ENV, WEBHOOK)
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return config, tmp_path / "seen.json"


@pytest.fixture
def fake(monkeypatch):
    """Fake Greenhouse board + fake Discord webhook in one transport.

    Set `board` to a response body (or an int HTTP status); set `discord` to the
    webhook's status. Posted Discord messages are collected in `posts`.
    """
    state = {
        "board": greenhouse_board((1, "Summer Trainee", "Helsinki")),
        "discord": 204,
        "posts": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "discord.test":
            state["posts"].append(json.loads(request.read()))
            return httpx.Response(state["discord"])
        body = state["board"]
        if isinstance(body, int):
            return httpx.Response(body)
        return httpx.Response(200, json=body)

    monkeypatch.setattr(
        cli, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return state


def run_cli(config, state, *extra):
    return cli.main(["run", "--config", str(config), "--state", str(state), *extra])


TWO_JOBS = greenhouse_board((1, "Summer Trainee", "Helsinki"), (2, "Data Trainee", "Espoo"))


def test_dry_run_prints_matches_and_saves_nothing(files, fake, capsys):
    config, state = files
    assert run_cli(config, state, "--dry-run") == 0
    assert "[seed] Acme – Summer Trainee" in capsys.readouterr().out
    assert not state.exists()
    assert fake["posts"] == []


def test_dry_run_needs_no_webhook(files, fake, monkeypatch):
    monkeypatch.delenv(cli.WEBHOOK_ENV)
    config, state = files
    assert run_cli(config, state, "--dry-run") == 0


def test_real_run_seeds_then_alerts(files, fake, capsys):
    config, state = files
    assert run_cli(config, state) == 0
    assert fake["posts"] == []  # first run seeds silently
    assert json.loads(state.read_text(encoding="utf-8"))["greenhouse:acme"]

    fake["board"] = TWO_JOBS
    assert run_cli(config, state) == 0
    assert "1 new job(s)" in capsys.readouterr().out
    (post,) = fake["posts"]
    assert "**Acme** – Data Trainee" in post["content"]


def test_nothing_new_sends_nothing(files, fake):
    config, state = files
    run_cli(config, state)
    run_cli(config, state)
    assert fake["posts"] == []


def test_failed_alert_keeps_jobs_new(files, fake):
    config, state = files
    run_cli(config, state)
    fake["board"] = TWO_JOBS
    fake["discord"] = 500
    assert run_cli(config, state) == 1
    assert "2" not in json.loads(state.read_text(encoding="utf-8"))["greenhouse:acme"]

    fake["discord"] = 204  # next run retries the same job
    assert run_cli(config, state) == 0
    assert len(fake["posts"]) == 2


def test_alert_error_does_not_log_the_webhook(files, fake, caplog):
    config, state = files
    run_cli(config, state)
    fake["board"] = TWO_JOBS
    fake["discord"] = 500
    run_cli(config, state)
    assert "secret-token" not in caplog.text
    assert "<webhook>" in caplog.text


def test_failed_source_exits_1_but_saves_state(files, fake):
    config, state = files
    fake["board"] = 503
    assert run_cli(config, state) == 1
    assert state.exists()


def test_missing_webhook_exits_2(files, fake, monkeypatch):
    monkeypatch.delenv(cli.WEBHOOK_ENV)
    config, state = files
    assert run_cli(config, state) == 2
    assert not state.exists()


def test_webhook_from_dotenv(files, fake, monkeypatch, tmp_path):
    monkeypatch.delenv(cli.WEBHOOK_ENV)
    (tmp_path / ".env").write_text(f"# local\n{cli.WEBHOOK_ENV}='{WEBHOOK}'\n", encoding="utf-8")
    config, state = files
    assert run_cli(config, state) == 0


def test_bad_config_exits_2(files, fake):
    config, state = files
    config.write_text("filters: {}\nsources: []\n", encoding="utf-8")
    assert run_cli(config, state) == 2


def test_missing_command_is_an_error():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
