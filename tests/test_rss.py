"""RSS adapter tests.

Fixtures are real feeds fetched 2026-11-18, trimmed to a few items with descriptions
cut short: Futurice and Kuva Space (Teamtailor) and Gofore (WordPress).
"""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from insidejob.adapters import rss
from insidejob.models import Workplace

FIXTURES = Path(__file__).parent / "fixtures"
FUTURICE = "careers.futurice.com/jobs.rss"


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def futurice():
    return rss.parse(load("rss_teamtailor_futurice.xml"), FUTURICE, "Futurice")


@pytest.fixture
def gofore():
    return rss.parse(load("rss_wordpress_gofore.xml"), "gofore.com/en/careers/feed/", "Gofore")


def test_teamtailor_ids_use_guid(futurice):
    assert futurice[1].id == f"rss:{FUTURICE}:d9956e22-9df8-40f2-af64-5b0d97a2a8cd"
    assert all(job.source == f"rss:{FUTURICE}" for job in futurice)


def test_teamtailor_fields(futurice):
    job = futurice[1]
    assert job.title == "Data & AI Principal (Technical)"
    assert job.url == "https://careers.futurice.com/jobs/8758856-data-ai-principal-technical"
    assert job.company == "Futurice"


def test_teamtailor_locations_joined(futurice):
    assert futurice[1].location == "Helsinki, Finland; Tampere, Finland"
    assert futurice[0].location == "London, United Kingdom"


@pytest.mark.parametrize(
    ("fixture", "index", "expected"),
    [
        ("rss_teamtailor_futurice.xml", 0, Workplace.REMOTE),  # remoteStatus "fully"
        ("rss_teamtailor_futurice.xml", 1, Workplace.HYBRID),
        ("rss_teamtailor_kuvaspace.xml", 0, Workplace.ONSITE),  # remoteStatus "none"
    ],
)
def test_remote_status_is_listed_workplace(fixture, index, expected):
    job = rss.parse(load(fixture), "x", "X")[index]
    assert job.workplace == expected
    assert job.inferred == frozenset()  # listed by the source, not guessed


def test_pubdate_is_timezone_aware(futurice):
    assert futurice[1].posted_at == datetime(2026, 11, 18, 6, 44, 20, tzinfo=UTC)


def test_description_is_plain_text(futurice, gofore):
    for job in [*futurice, *gofore]:
        assert job.description
        assert "<" not in job.description
        assert "&lt;" not in job.description
    assert futurice[1].description.startswith("About the role")


def test_wordpress_uses_full_content_and_guid(gofore):
    job = gofore[0]
    assert job.title == "Space Software Summer Trainee"
    assert (
        job.id
        == "rss:gofore.com/en/careers/feed/:https://gofore.com/job/space-software-summer-trainee/"
    )
    assert job.url == "https://gofore.com/en/careers/space-software-summer-trainee/"
    assert job.description.startswith("We are looking for Space Software Summer Trainee")


def test_wordpress_has_no_location_or_workplace(gofore):
    assert gofore[0].location == ""
    assert gofore[0].workplace is None


def test_minimal_feed_without_guid_uses_link():
    raw = """<rss version="2.0"><channel><title>X</title>
      <item><title> Summer Intern </title><link>https://example.com/1</link></item>
    </channel></rss>"""
    (job,) = rss.parse(raw, "example.com/feed", "Example")
    assert job.id == "rss:example.com/feed:https://example.com/1"
    assert job.title == "Summer Intern"
    assert job.posted_at is None
    assert job.description == ""


def test_item_without_guid_or_link_is_an_error():
    raw = "<rss><channel><item><title>x</title></item></channel></rss>"
    with pytest.raises(ValueError, match="without guid or link"):
        rss.parse(raw, "example.com/feed", "Example")


def test_unknown_remote_status_stays_unknown():
    raw = """<rss><channel><item><title>x</title><guid>1</guid>
      <remoteStatus>temporary</remoteStatus></item></channel></rss>"""
    (job,) = rss.parse(raw, "b", "B")
    assert job.workplace is None


def test_bad_pubdate_is_ignored():
    raw = (
        "<rss><channel><item><guid>1</guid><title>x</title>"
        "<pubDate>soon</pubDate></item></channel></rss>"
    )
    (job,) = rss.parse(raw, "b", "B")
    assert job.posted_at is None


def test_empty_feed():
    assert rss.parse("<rss><channel><title>x</title></channel></rss>", "b", "B") == []


def test_fetch_adds_https():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, content=load("rss_teamtailor_kuvaspace.xml"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = rss.fetch(client, "careers.kuvaspace.com/jobs.rss")
    assert seen["url"] == "https://careers.kuvaspace.com/jobs.rss"
    assert len(rss.parse(raw, "careers.kuvaspace.com/jobs.rss", "Kuva Space")) == 1


def test_fetch_keeps_explicit_scheme():
    assert rss.feed_url("http://example.com/feed") == "http://example.com/feed"
