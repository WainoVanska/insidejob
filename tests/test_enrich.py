"""enrich heuristics, on real-style EN and FI snippets."""

from datetime import date

import pytest

from insidejob.enrich import enrich
from insidejob.models import Employment, Workplace
from tests.helpers import make_job


@pytest.mark.parametrize(
    ("title", "location", "description", "expected"),
    [
        ("Trainee", "Helsinki", "We work hybrid: 3 days a week in the office.", Workplace.HYBRID),
        ("Trainee", "Hybrid - Helsinki, Finland", "", Workplace.HYBRID),
        ("Trainee", "Remote - EMEA", "", Workplace.REMOTE),
        ("Trainee", "Helsinki", "This is a fully remote position.", Workplace.REMOTE),
        ("Trainee", "Helsinki", "Työ tehdään etätyönä.", Workplace.REMOTE),
        ("Trainee", "Helsinki", "Työskentelet hybridimallissa.", Workplace.HYBRID),
        ("Trainee", "Helsinki", "You'll work on-site at our Espoo campus.", Workplace.ONSITE),
        ("Trainee", "Helsinki", "Lähityö Vantaan toimistolla.", Workplace.ONSITE),
        # Location wins over a vaguer description.
        ("Trainee", "Remote, Finland", "Visit the office on-site sometimes.", Workplace.REMOTE),
    ],
)
def test_workplace(title, location, description, expected):
    job = enrich(make_job(title=title, location=location, description=description))
    assert job.workplace == expected
    assert "workplace" in job.inferred


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("Software Engineering Intern", "", Employment.INTERNSHIP),
        ("Kesäharjoittelija, data", "", Employment.INTERNSHIP),
        ("Junior Marketing Artist (6 Month FTC)", "", Employment.FIXED_TERM),
        ("Junior Developer", "This is a part-time role, 20 h/week.", Employment.PART_TIME),
        ("Junior Developer", "Tehtävä on määräaikainen.", Employment.FIXED_TERM),
        ("Junior Developer", "A permanent, full-time position.", Employment.FULL_TIME),
        ("Junior Developer", "Vakituinen kokoaikainen työsuhde.", Employment.FULL_TIME),
        # The title is more specific than the description.
        ("Summer Trainee", "We offer full-time roles too.", Employment.INTERNSHIP),
    ],
)
def test_employment(title, description, expected):
    job = enrich(make_job(title=title, description=description))
    assert job.employment == expected
    assert "employment" in job.inferred


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("Summer Trainee 2027", "", None),
        ("Summer Internship 2027", "", None),
        ("Trainee", "Join us for summer 2027!", "summer 2027"),
        ("Trainee", "Kesällä 2027 alkava harjoittelu.", "summer 2027"),
        ("Trainee", "The internship starts in June 2027.", "Jun 2027"),
        ("Trainee", "Starting date: 1 June", "Jun"),
        ("Trainee", "Start date: January 15, 2027", "Jan 2027"),
        ("Trainee", "Starting from September", "Sep"),
        ("Trainee", "Kesäkuusta 2027 alkaen.", "Jun 2027"),
        ("Trainee", "Toukokuun alkaen", "May"),
        ("Trainee", "We'd like you to start as soon as possible.", "asap"),
        ("Trainee", "Hakemukset 15.1. mennessä.", None),
    ],
)
def test_start(title, description, expected):
    job = enrich(make_job(title=title, description=description))
    assert job.start == expected
    assert ("start" in job.inferred) == (expected is not None)


def test_summer_year_in_title():
    assert enrich(make_job(title="Summer 2027 Trainee")).start == "summer 2027"


def test_listed_values_are_kept():
    job = make_job(
        title="Summer Intern",
        location="Remote",
        workplace=Workplace.ONSITE,
        employment=Employment.FULL_TIME,
        start="Jun 2027",
    )
    enriched = enrich(job)
    assert enriched.workplace == Workplace.ONSITE
    assert enriched.employment == Employment.FULL_TIME
    assert enriched.start == "Jun 2027"
    assert enriched.inferred == frozenset()


def test_no_signal_leaves_job_unchanged():
    job = make_job(title="Data Analyst", location="Helsinki", description="Great team.")
    assert enrich(job) is job


def test_deadline_is_never_inferred():
    assert enrich(make_job(description="Apply by 15.1.2027")).deadline is None
    assert enrich(make_job(deadline=date(2027, 1, 15))).deadline == date(2027, 1, 15)
