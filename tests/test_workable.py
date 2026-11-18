"""Workable adapter tests.

Fixture: Varjo's real widget response with `details=true` (fetched 2026-11-18),
descriptions cut short.
"""

from datetime import UTC, datetime

import httpx
import pytest

from insidejob.adapters import workable
from insidejob.models import Employment, Workplace


@pytest.fixture
def jobs(load_fixture):
    return workable.parse(load_fixture("workable_varjo.json"), "varjo-1", "Varjo")


def test_fields(jobs):
    job = jobs[0]
    assert job.id == "workable:varjo-1:66D564EA34"
    assert job.source == "workable:varjo-1"
    assert job.title == "Computer Vision Engineer, C++"
    assert job.location == "Helsinki, Finland"
    assert job.url == "https://apply.workable.com/j/66D564EA34"
    assert job.posted_at == datetime(2026, 9, 23, tzinfo=UTC)


def test_description_is_plain_text(jobs):
    assert jobs[0].description.startswith("Varjo is the world-leading provider")
    assert all("<" not in job.description for job in jobs)


def test_not_telecommuting_leaves_workplace_unknown(jobs):
    assert all(job.workplace is None for job in jobs)


def job_with(**fields) -> dict:
    return {"jobs": [{"shortcode": "ABC", "title": "Trainee", "url": "https://x/ABC"} | fields]}


def test_telecommuting_is_remote():
    (job,) = workable.parse(job_with(telecommuting=True), "acme", "Acme")
    assert job.workplace == Workplace.REMOTE


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Full-time", Employment.FULL_TIME),
        ("Part-time", Employment.PART_TIME),
        ("Internship", Employment.INTERNSHIP),
        ("Contract", Employment.FIXED_TERM),
        ("", None),
        (None, None),
    ],
)
def test_employment(value, expected):
    (job,) = workable.parse(job_with(employment_type=value), "acme", "Acme")
    assert job.employment == expected


def test_multiple_locations():
    raw = job_with(
        locations=[
            {"city": "Helsinki", "country": "Finland"},
            {"city": "Tampere", "country": "Finland"},
            {"city": "Helsinki", "country": "Finland"},
        ]
    )
    (job,) = workable.parse(raw, "acme", "Acme")
    assert job.location == "Helsinki, Finland; Tampere, Finland"


def test_falls_back_to_city_and_country():
    (job,) = workable.parse(job_with(city="Espoo", country="Finland"), "acme", "Acme")
    assert job.location == "Espoo, Finland"


def test_missing_optional_fields():
    (job,) = workable.parse(job_with(), "acme", "Acme")
    assert job.location == ""
    assert job.posted_at is None
    assert job.description == ""


def test_fetch_asks_for_details(load_fixture):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=load_fixture("workable_varjo.json"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = workable.fetch(client, "varjo-1")
    assert seen["url"] == "https://apply.workable.com/api/v1/widget/accounts/varjo-1?details=true"
    assert len(raw["jobs"]) == 2
