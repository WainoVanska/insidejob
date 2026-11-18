"""Filter behaviour with the real filters from config.yaml.

Titles are real ones seen on the target boards (2026-11-18) plus Finnish variants.
"""

from pathlib import Path

import pytest

from insidejob.config import load_config
from insidejob.filters import matches
from insidejob.models import Job

FILTERS = load_config(Path(__file__).parent.parent / "config.yaml").sources[0].filters


def job(title: str, location: str = "Helsinki, Finland") -> Job:
    return Job(
        id="greenhouse:acme:1",
        source="greenhouse:acme",
        company="Acme",
        title=title,
        location=location,
        url="https://example.com",
    )


@pytest.mark.parametrize(
    "title",
    [
        "Internal Communications & Employer Branding Trainee",
        "Junior Accounts Receivable Specialist",
        "Junior Marketing Artist (6 Month FTC)",
        "Software Engineering Intern",
        "Summer Internship 2027 – Data",
        "Thesis Worker, Machine Learning",
        "Graduate Program 2027",
        "Kesätyöntekijä, asiakaspalvelu",
        "Harjoittelija, ohjelmistokehitys",
        "Opinnäytetyöntekijä",
        "Diplomityöntekijä: tekoäly",
        "Space Software Summer Trainee",
    ],
)
def test_relevant_titles_match(title):
    assert matches(job(title), FILTERS)


@pytest.mark.parametrize(
    "title",
    [
        "Internal Communications Manager",  # "Internal" must not count as "intern"
        "International Sales Representative",
        "Senior AI Software Engineer",
        "Lead Product Designer | Platform Engineering",
        "Staff Product Security Engineer",
        "Sr. Junior Program Director",  # exclude wins over include
        "Head of People Operations - EMEA",
        "Engineering Manager, Summer Projects",
        "Account Executive, Manufacturing (SEA)",
    ],
)
def test_irrelevant_titles_do_not_match(title):
    assert not matches(job(title), FILTERS)


@pytest.mark.parametrize(
    "location",
    [
        "Helsinki, Finland",
        "Helsinki HQ",
        "Espoo",
        "Vantaa, Finland",
        "Tampere, Finland",
        "Lisbon, Portugal; Helsinki, Finland",
        "Remote - EMEA",
        "Remote, Europe",
        "",  # unknown location passes rather than risking a missed job
    ],
)
def test_matching_locations(location):
    assert matches(job("Summer Trainee", location), FILTERS)


@pytest.mark.parametrize(
    "location",
    ["Leuven", "Remote - United States", "US Remote", "Bangkok, Thailand", "Stockholm, Sweden"],
)
def test_other_locations_filtered_out(location):
    assert not matches(job("Summer Trainee", location), FILTERS)
