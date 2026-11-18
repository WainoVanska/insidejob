"""Greenhouse adapter tests.

Fixture: a real RELEX response (`?content=true`, fetched 2026-11-18), trimmed to four
jobs with descriptions cut to two paragraphs. One hand edit: the last job's
`application_deadline` is set to a value in the format seen on Oura's board, because
RELEX has no deadlines.
"""

from datetime import date, datetime

import httpx
import pytest

from insidejob.adapters import greenhouse
from insidejob.models import Job


@pytest.fixture
def jobs(load_fixture) -> list[Job]:
    return greenhouse.parse(load_fixture("greenhouse_relex.json"), "relex", "RELEX Solutions")


def test_parses_every_job(jobs):
    assert len(jobs) == 4


def test_ids_are_prefixed_with_source(jobs):
    assert jobs[0].id == "greenhouse:relex:8014266003"
    assert all(job.source == "greenhouse:relex" for job in jobs)


def test_company_comes_from_config_not_response(load_fixture):
    jobs = greenhouse.parse(load_fixture("greenhouse_relex.json"), "relex", "RELEX")
    assert {job.company for job in jobs} == {"RELEX"}


def test_titles_are_stripped(jobs):
    # The API returns "…Branding Trainee " with a trailing space.
    assert jobs[0].title == "Internal Communications & Employer Branding Trainee"


def test_multiple_locations_stay_joined(jobs):
    assert jobs[2].location == "Lisbon, Portugal; London, United Kingdom"


def test_url_is_the_public_posting(jobs):
    assert jobs[0].url == "https://www.relexsolutions.com/careers/jobs/?gh_jid=8014266003"


def test_posted_at_is_timezone_aware(jobs):
    posted = jobs[0].posted_at
    assert isinstance(posted, datetime)
    assert posted.tzinfo is not None
    assert posted.date() == date(2026, 10, 6)


def test_deadline_parsed_when_present(jobs):
    assert jobs[3].deadline == date(2027, 1, 15)


def test_deadline_none_when_missing(jobs):
    assert jobs[0].deadline is None


def test_description_is_plain_text(jobs):
    for job in jobs:
        assert job.description
        assert "<" not in job.description
        assert "&lt;" not in job.description
        assert "&amp;" not in job.description
    assert "3-month traineeship" in jobs[0].description


def test_unlisted_details_are_unknown(jobs):
    job = jobs[0]
    assert job.workplace is None
    assert job.employment is None
    assert job.start is None
    assert job.inferred == frozenset()


def test_empty_board():
    assert greenhouse.parse({"jobs": []}, "relex", "RELEX Solutions") == []


def test_missing_optional_fields():
    raw = {
        "jobs": [
            {
                "id": 1,
                "title": "Summer Trainee",
                "absolute_url": "https://example.com/1",
                "location": None,
                "first_published": None,
            }
        ]
    }
    (job,) = greenhouse.parse(raw, "acme", "Acme")
    assert job.location == ""
    assert job.posted_at is None
    assert job.deadline is None
    assert job.description == ""


def test_fetch_requests_content(load_fixture):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=load_fixture("greenhouse_relex.json"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = greenhouse.fetch(client, "relex")

    assert seen["url"] == "https://boards-api.greenhouse.io/v1/boards/relex/jobs?content=true"
    assert len(raw["jobs"]) == 4


def test_fetch_raises_on_http_error():
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    with httpx.Client(transport=transport) as client, pytest.raises(httpx.HTTPStatusError):
        greenhouse.fetch(client, "no-such-board")
