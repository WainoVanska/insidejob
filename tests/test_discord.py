import json
from datetime import date

import httpx
import pytest

from insidejob.models import Employment, Workplace
from insidejob.notify.discord import (
    EMBED_CHARS_PER_MESSAGE,
    EMBEDS_PER_MESSAGE,
    DiscordNotifier,
    build_payloads,
    embed_size,
    escape,
    job_embed,
)
from insidejob.rank import Rank, RankedJob
from tests.helpers import make_job

WEBHOOK = "https://discord.test/api/webhooks/1/token"


def ranked(*jobs, stars: int = 1, reasons: tuple[str, ...] = ()) -> list[RankedJob]:
    """Wrap jobs as already-ranked items (ranking itself is tested elsewhere)."""
    return [RankedJob(job, Rank(0, stars, reasons)) for job in jobs]


def test_embed_layout():
    job = make_job(
        company="RELEX",
        title="Summer Trainee, Data Science",
        location="Helsinki",
        workplace=Workplace.HYBRID,
        employment=Employment.INTERNSHIP,
        start="Jun 2027",
        deadline=date(2027, 1, 15),
        inferred={"start"},
        url="https://example.com/1",
    )
    rank = Rank(10.5, 3, ("intern +3", "Helsinki +3"), 13, ("Helsinki",))
    assert job_embed(job, rank) == {
        "author": {"name": "RELEX"},
        "title": "Summer Trainee, Data Science",
        "url": "https://example.com/1",
        "color": 0x2ECC71,
        "description": (
            "**🟢 10.5 / 13**\n"
            "📍 Helsinki · 🏢 hybrid · 💼 internship · 🗓️ ~starts Jun 2027 · ⏳ apply by 15.1.2027\n"
            "💡 intern +3 · Helsinki +3"
        ),
    }


@pytest.mark.parametrize(("stars", "colour"), [(3, 0x2ECC71), (2, 0xF1C40F), (1, 0xE74C3C)])
def test_bar_colour_follows_match_level(stars, colour):
    assert job_embed(make_job(), Rank(5, stars))["color"] == colour


def test_unranked_job_is_grey_without_score():
    embed = job_embed(make_job(location=""))
    assert embed["color"] == 0x99AAB5
    assert "description" not in embed


def test_markdown_is_escaped_in_the_description_only():
    embed = job_embed(make_job(title="C++ *Intern*", location="Espoo_HQ"), Rank(5, 1))
    assert embed["title"] == "C++ *Intern*"  # embed titles don't render markdown
    assert "Espoo\\_HQ" in embed["description"]
    assert escape("~~gone~~") == r"\~\~gone\~\~"


def test_long_title_is_cut_to_discord_limit():
    embed = job_embed(make_job(title="x" * 300))
    assert len(embed["title"]) == 256
    assert embed["title"].endswith("…")


def test_one_payload_with_header():
    (payload,) = build_payloads(ranked(make_job("1"), make_job("2")))
    assert payload["content"] == "🔍 **2 new jobs**"
    assert len(payload["embeds"]) == 2
    assert payload["allowed_mentions"] == {"parse": []}


def test_header_singular():
    assert build_payloads(ranked(make_job()))[0]["content"] == "🔍 **1 new job**"


def test_splits_at_ten_embeds_and_keeps_order():
    payloads = build_payloads(ranked(*(make_job(str(i), title=f"Job {i}") for i in range(23))))
    assert [len(p["embeds"]) for p in payloads] == [10, 10, 3]
    assert "content" not in payloads[1]
    titles = [e["title"] for p in payloads for e in p["embeds"]]
    assert titles == [f"Job {i}" for i in range(23)]


def test_splits_on_embed_characters():
    jobs = [make_job(str(i), title="T" * 250, location="L" * 900) for i in range(9)]
    payloads = build_payloads(ranked(*jobs))
    assert len(payloads) > 1
    for payload in payloads:
        assert len(payload["embeds"]) <= EMBEDS_PER_MESSAGE
        assert sum(embed_size(e) for e in payload["embeds"]) <= EMBED_CHARS_PER_MESSAGE


def recording_client(statuses: list[int]):
    """Fake webhook: returns the given statuses in order, records posted payloads."""
    posted = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(request)
        status = statuses.pop(0) if statuses else 204
        if status == 429:
            return httpx.Response(429, json={"retry_after": 0.5})
        return httpx.Response(status)

    return httpx.Client(transport=httpx.MockTransport(handler)), posted


def test_send_posts_embeds_with_mentions_disabled():
    client, posted = recording_client([204])
    DiscordNotifier(WEBHOOK, client, sleep=lambda _: None).send(ranked(make_job()))
    (request,) = posted
    assert str(request.url) == WEBHOOK
    body = json.loads(request.read())
    assert body["allowed_mentions"] == {"parse": []}
    assert body["embeds"][0]["url"] == "https://example.com/1"


def test_send_pauses_between_messages():
    client, posted = recording_client([])
    pauses = []
    jobs = [make_job(str(i)) for i in range(25)]
    DiscordNotifier(WEBHOOK, client, pause=1.0, sleep=pauses.append).send(ranked(*jobs))
    assert len(posted) == 3
    assert len(pauses) == 2


def test_rate_limit_is_retried_once():
    client, posted = recording_client([429, 204])
    waits = []
    DiscordNotifier(WEBHOOK, client, sleep=waits.append).send(ranked(make_job()))
    assert len(posted) == 2
    assert waits == [0.5]


def test_failure_raises():
    client, _ = recording_client([500])
    with pytest.raises(httpx.HTTPStatusError):
        DiscordNotifier(WEBHOOK, client, sleep=lambda _: None).send(ranked(make_job()))
