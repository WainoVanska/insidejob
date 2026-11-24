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
    # Neutral default ranking: title 3 of max 5 (title 3 + deadline 2) = 60 % → yellow.
    assert "[seed] 🟡 Acme – Summer Trainee · 3 / 5" in out
    assert "↳ intern +3" in out
    assert not state.exists()
    assert fake["posts"] == []


def test_dry_run_needs_no_webhook(files, fake, monkeypatch):
    monkeypatch.delenv(cli.WEBHOOK_ENV)
    config, state = files
    assert run_cli(config, state, "--dry-run") == 0


def seed(config, state, fake):
    """First run: records the board and sends the welcome message; then clear posts."""
    assert run_cli(config, state) == 0
    fake["posts"].clear()


def test_real_run_seeds_then_alerts(files, fake, capsys):
    config, state = files
    assert run_cli(config, state) == 0
    (welcome,) = fake["posts"]  # first run: no job alerts, only the welcome message
    assert welcome["content"].startswith("✅ **insidejob is set up!** Watching 1 company")
    assert json.loads(state.read_text(encoding="utf-8"))["greenhouse:acme"]

    fake["posts"].clear()
    fake["board"] = TWO_JOBS
    assert run_cli(config, state) == 0
    assert "1 new job(s)" in capsys.readouterr().out
    (post,) = fake["posts"]
    assert post["content"] == "🆕 **1 new job**"
    (embed,) = post["embeds"]
    assert (embed["author"]["name"], embed["title"]) == ("Acme", "🆕 Data Trainee")


def test_nothing_new_sends_nothing(files, fake):
    config, state = files
    seed(config, state, fake)
    run_cli(config, state)
    assert fake["posts"] == []


def test_failed_alert_keeps_jobs_new(files, fake):
    config, state = files
    seed(config, state, fake)
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
    seed(config, state, fake)  # job 1
    before = state.read_text(encoding="utf-8")

    fake["board"] = TWO_JOBS
    assert run_top(config, state, "--count", "5") == 0
    assert state.read_text(encoding="utf-8") == before  # job 2 not recorded
    (post,) = fake["posts"]
    assert post["content"] == "🏆 **Top 2 jobs right now**"
    assert len(post["embeds"]) == 2


def test_top_marks_recently_seen_jobs_fresh(files, fake):
    config, state = files
    seed(config, state, fake)  # board seeded today: job 1 first seen today
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


def test_welcome_shows_the_best_three_matches(files, fake):
    config, state = files
    fake["board"] = greenhouse_board(
        *((i, f"Trainee {i}", "Helsinki") for i in range(1, 6)), (9, "Chef", "Helsinki")
    )
    assert run_cli(config, state) == 0
    (post,) = fake["posts"]
    assert "Watching 1 company · 5 matching jobs right now" in post["content"]
    assert "The best 3 matches open now:" in post["content"]
    assert len(post["embeds"]) == 3
    assert not any(e["title"].startswith("🆕") for e in post["embeds"])


def test_failed_welcome_still_saves_state_and_exits_1(files, fake):
    config, state = files
    fake["discord"] = 500
    assert run_cli(config, state) == 1
    assert state.exists()  # seeding worked: the next run is a normal run
    fake["discord"] = 204
    fake["posts"].clear()
    assert run_cli(config, state) == 0
    assert fake["posts"] == []  # no second welcome, nothing new


def test_no_welcome_when_every_source_failed(files, fake):
    config, state = files
    fake["board"] = 503
    assert run_cli(config, state) == 1
    assert fake["posts"] == []


def test_dry_run_sends_no_welcome(files, fake):
    config, state = files
    run_cli(config, state, "--dry-run")
    assert fake["posts"] == []


def run_check(config):
    return cli.main(["check", "--config", str(config)])


@pytest.fixture
def actions(tmp_path, monkeypatch):
    """Pretend to be GitHub Actions: annotations on, job summary written to a file."""
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    return summary


def test_check_previews_matches_and_sends_nothing(files, fake, actions, capsys):
    config, state = files
    fake["board"] = TWO_JOBS
    assert run_check(config) == 0
    out = capsys.readouterr().out
    assert "Config OK. Watching 1 company: Acme" in out
    assert "Top 2 of 2 matching job(s)" in out
    assert fake["posts"] == []
    assert not state.exists()
    summary = actions.read_text(encoding="utf-8")
    assert "Watching 1 company · 2 matching jobs now" in summary
    assert "| Acme | 2 | 2 |" in summary
    assert "[Summer Trainee](https://example.com/1)" in summary


def test_check_needs_no_webhook(files, fake, monkeypatch):
    monkeypatch.delenv(cli.WEBHOOK_ENV)
    config, _ = files
    assert run_check(config) == 0


def test_check_bad_config_exits_1_with_an_annotation(files, fake, actions, capsys):
    config, _ = files
    config.write_text("looking_for: {roles: [ceo]}\ncompanies: [x]\n", encoding="utf-8")
    assert run_check(config) == 1
    assert "::error title=Config problem::" in capsys.readouterr().out
    assert "has a problem" in actions.read_text(encoding="utf-8")


def test_check_dead_board_exits_1(files, fake, actions, capsys):
    config, _ = files
    fake["board"] = 404
    assert run_check(config) == 1
    assert "::error title=Company not reachable::Acme" in capsys.readouterr().out
    assert "| ❌ Acme | failed | |" in actions.read_text(encoding="utf-8")


def test_check_prints_no_annotations_locally(files, fake, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    config, _ = files
    fake["board"] = 404
    assert run_check(config) == 1
    assert "::error" not in capsys.readouterr().out


def test_presets_command_reports_failures(fake, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    presets = tmp_path / "presets"
    presets.mkdir()
    (presets / "one.yaml").write_text(
        "companies: ['Acme: https://job-boards.greenhouse.io/acme']\n", encoding="utf-8"
    )
    report = tmp_path / "report.md"
    assert cli.main(["presets", "--dir", str(presets), "--report", str(report)]) == 0
    assert "All preset boards OK" in report.read_text(encoding="utf-8")

    fake["board"] = 404
    assert cli.main(["presets", "--dir", str(presets), "--report", str(report)]) == 1
    text = report.read_text(encoding="utf-8")
    assert "Some preset job boards failed" in text
    assert "`greenhouse:acme`" in text
    assert fake["posts"] == []


def test_heartbeat_posts_check_in_even_with_nothing_new(files, fake):
    config, state = files
    run_cli(config, state)  # first run: seeds and sends the welcome message
    fake["posts"].clear()
    assert run_cli(config, state, "--heartbeat") == 0
    (post,) = fake["posts"]
    assert post["content"].startswith("🩺 **Weekly check-in** · 1 company checked")
    assert "all boards OK" in post["content"]


def test_no_heartbeat_without_flag(files, fake):
    config, state = files
    run_cli(config, state)
    fake["posts"].clear()
    run_cli(config, state)
    assert fake["posts"] == []


def test_heartbeat_shows_failing_board_since_first_failure(files, fake):
    config, state = files
    run_cli(config, state)
    fake["posts"].clear()
    fake["board"] = 503
    assert run_cli(config, state, "--heartbeat") == 1
    (post,) = fake["posts"]
    (card,) = post["embeds"]
    assert card["author"]["name"] == "Acme"
    assert card["title"].startswith("⚠️ Failing since ")
    health = json.loads((state.parent / "health.json").read_text(encoding="utf-8"))
    assert "failing_since" in health["greenhouse:acme"]


def test_dry_run_writes_no_health(files, fake):
    config, state = files
    run_cli(config, state, "--dry-run", "--heartbeat")
    assert not (state.parent / "health.json").exists()
    assert fake["posts"] == []
