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
    out = capsys.readouterr().out
    assert "[seed] 🟡 Acme – Summer Trainee · 6 / 13" in out
    assert "↳ intern +3 · Helsinki +3" in out
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
    assert post["content"] == "🆕 **1 new job**"
    (embed,) = post["embeds"]
    assert (embed["author"]["name"], embed["title"]) == ("Acme", "🆕 Data Trainee")


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


def run_top(config, state, *extra):
    return cli.main(["top", "--config", str(config), "--state", str(state), *extra])


def test_top_sends_best_jobs_and_never_writes_state(files, fake):
    config, state = files
    run_cli(config, state)  # seed job 1
    before = state.read_text(encoding="utf-8")

    fake["board"] = TWO_JOBS
    assert run_top(config, state, "--count", "5") == 0
    assert state.read_text(encoding="utf-8") == before  # job 2 not recorded
    (post,) = fake["posts"]
    assert post["content"] == "🏆 **Top 2 jobs right now**"
    assert len(post["embeds"]) == 2


def test_top_marks_recently_seen_jobs_fresh(files, fake):
    config, state = files
    run_cli(config, state)  # board seeded today: job 1 first seen today
    fake["board"] = TWO_JOBS  # job 2 is brand new
    run_top(config, state)
    titles = [e["title"] for e in fake["posts"][0]["embeds"]]
    assert sorted(titles) == ["🆕 Data Trainee", "🆕 Summer Trainee"]


def test_top_marks_nothing_fresh_on_an_unknown_board(files, fake):
    config, state = files  # no state at all: everything would look new
    run_top(config, state)
    (embed,) = fake["posts"][0]["embeds"]
    assert embed["title"] == "Summer Trainee"


def test_top_old_jobs_are_not_fresh(files, fake):
    config, state = files
    state.write_text(
        json.dumps(
            {"greenhouse:acme": {"1": {"first_seen": "2026-01-01", "last_seen": "2026-01-01"}}}
        ),
        encoding="utf-8",
    )
    run_top(config, state)
    (embed,) = fake["posts"][0]["embeds"]
    assert embed["title"] == "Summer Trainee"


def test_top_count_limits_and_dry_run_sends_nothing(files, fake, capsys):
    config, state = files
    fake["board"] = TWO_JOBS
    assert run_top(config, state, "--count", "1", "--dry-run") == 0
    assert "top 1 job(s)" in capsys.readouterr().out
    assert fake["posts"] == []


@pytest.mark.parametrize("count", ["0", "-3", "ten"])
def test_top_count_must_be_positive(files, count):
    config, state = files
    with pytest.raises(SystemExit) as exc:
        run_top(config, state, "--count", count)
    assert exc.value.code == 2
