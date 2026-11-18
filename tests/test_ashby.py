"""Ashby adapter tests.

Fixture: real ICEYE postings (fetched 2026-11-18) with descriptions cut short, plus the
one unlisted posting seen on Supercell's board.
"""

from datetime import UTC, datetime

import httpx
import pytest

from insidejob.adapters import ashby
from insidejob.models import Employment, Workplace


@pytest.fixture
def jobs(load_fixture):
    return ashby.parse(load_fixture("ashby_iceye.json"), "iceye", "ICEYE")


def test_unlisted_postings_are_skipped(jobs):
    assert len(jobs) == 4
    assert all("Unlisted" not in job.title for job in jobs)


def test_ids_and_urls(jobs):
    job = jobs[0]
    assert job.id == "ashby:iceye:1b8f590b-fd9a-4c7a-ae0d-6e15f0bed42f"
    assert job.source == "ashby:iceye"
    assert job.url == "https://jobs.ashbyhq.com/iceye/1b8f590b-fd9a-4c7a-ae0d-6e15f0bed42f"
    assert job.title == "ICEYE Engineering Intern Lab 2027"


def test_locations_include_country_and_secondaries(jobs):
    assert jobs[0].location == "Espoo, Finland; Valencia, Spain; Warsaw, Poland"
    assert jobs[2].location == "France"  # country already in the name: not repeated
    assert jobs[3].location == "Berlin, Germany"


def test_workplace_is_listed(jobs):
    assert [job.workplace for job in jobs] == [
        Workplace.HYBRID,
        Workplace.ONSITE,
        Workplace.REMOTE,
        None,  # workplaceType missing
    ]
    assert all(job.inferred == frozenset() for job in jobs)


def test_employment_is_listed(jobs):
    # ICEYE lists its intern roles as FullTime: we keep what the source says.
    assert jobs[0].employment == Employment.FULL_TIME


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PartTime", Employment.PART_TIME),
        ("Intern", Employment.INTERNSHIP),
        ("Contract", Employment.FIXED_TERM),
        ("Temporary", Employment.FIXED_TERM),
        ("Something", None),
        (None, None),
    ],
)
def test_employment_mapping(value, expected):
    raw = {"jobs": [{"id": "1", "title": "x", "jobUrl": "u", "employmentType": value}]}
    assert ashby.parse(raw, "b", "B")[0].employment == expected


def test_posted_at(jobs):
    assert jobs[0].posted_at == datetime(2026, 10, 22, 14, 13, 57, 226000, tzinfo=UTC)


def test_description_is_plain_text(jobs):
    assert all(job.description and "<" not in job.description for job in jobs)


def test_minimal_job():
    raw = {"jobs": [{"id": "1", "title": " Summer Intern ", "jobUrl": "https://x/1"}]}
    (job,) = ashby.parse(raw, "acme", "Acme")
    assert job.title == "Summer Intern"
    assert job.location == ""
    assert job.posted_at is None
    assert job.workplace is None


def test_string_secondary_locations_are_accepted():
    raw = {
        "jobs": [
            {
                "id": "1",
                "title": "x",
                "jobUrl": "u",
                "location": "Helsinki",
                "secondaryLocations": ["Tampere", "Helsinki"],
            }
        ]
    }
    assert ashby.parse(raw, "b", "B")[0].location == "Helsinki; Tampere"


def test_empty_board():
    assert ashby.parse({"jobs": []}, "iceye", "ICEYE") == []


def test_fetch(load_fixture):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=load_fixture("ashby_iceye.json"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = ashby.fetch(client, "iceye")
    assert seen["url"] == (
        "https://api.ashbyhq.com/posting-api/job-board/iceye?includeCompensation=false"
    )
    assert len(raw["jobs"]) == 5
