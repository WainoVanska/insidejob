from datetime import date

import httpx
import pytest

from insidejob.models import Employment, Workplace
from insidejob.notify.discord import (
    MESSAGE_LIMIT,
    DiscordNotifier,
    build_messages,
    escape,
    format_job,
)
from tests.helpers import make_job

WEBHOOK = "https://discord.test/api/webhooks/1/token"


def test_format_matches_agreed_layout():
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
    assert format_job(job) == (
        "**RELEX** – Summer Trainee, Data Science\n"
        "Helsinki · hybrid · internship · ~start Jun 2027 · apply by 15.1.2027"
        " · <https://example.com/1>"
    )


def test_unknown_fields_are_left_out():
    job = make_job(location="", url="https://example.com/1")
    assert format_job(job).splitlines()[1] == "<https://example.com/1>"


def test_markdown_in_titles_is_escaped():
    assert escape("C++ *Intern* _2027_ | ~x~") == r"C++ \*Intern\* \_2027\_ \| ~x~"
    assert escape("~~gone~~") == r"\~\~gone\~\~"


def test_single_message_has_header():
    (message,) = build_messages([make_job("1"), make_job("2")])
    assert message.startswith("**2 new jobs**\n\n**Acme**")
    assert message.count("<https://example.com/") == 2


def test_header_singular():
    assert build_messages([make_job()])[0].startswith("**1 new job**\n\n")


def test_splits_at_limit_without_breaking_jobs():
    jobs = [make_job(str(i), title="Trainee " + "x" * 150) for i in range(40)]
    messages = build_messages(jobs)
    assert len(messages) > 1
    assert all(len(m) <= MESSAGE_LIMIT for m in messages)
    assert sum(m.count("<https://") for m in messages) == 40
    for message in messages:  # every job block stays whole: title line + detail line
        assert message.count("**Acme**") == message.count("<https://")


def test_oversized_job_is_truncated():
    (message,) = build_messages([make_job(title="x" * 3000)])
    assert len(message) <= MESSAGE_LIMIT
    assert message.startswith("**1 new job**\n\n**Acme**")
    assert message.endswith("…")


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


def test_send_posts_with_mentions_disabled():
    client, posted = recording_client([204])
    DiscordNotifier(WEBHOOK, client, sleep=lambda _: None).send([make_job()])
    (request,) = posted
    assert str(request.url) == WEBHOOK
    body = request.read().decode()
    assert '"allowed_mentions":{"parse":[]}' in body.replace(" ", "")


def test_send_pauses_between_messages():
    client, posted = recording_client([])
    pauses = []
    jobs = [make_job(str(i), title="Trainee " + "x" * 150) for i in range(40)]
    DiscordNotifier(WEBHOOK, client, pause=1.0, sleep=pauses.append).send(jobs)
    assert len(pauses) == len(posted) - 1


def test_rate_limit_is_retried_once():
    client, posted = recording_client([429, 204])
    waits = []
    DiscordNotifier(WEBHOOK, client, sleep=waits.append).send([make_job()])
    assert len(posted) == 2
    assert waits == [0.5]


def test_failure_raises():
    client, _ = recording_client([500])
    with pytest.raises(httpx.HTTPStatusError):
        DiscordNotifier(WEBHOOK, client, sleep=lambda _: None).send([make_job()])
