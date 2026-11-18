"""The experience penalty and the title-only AI rule.

The core ranking rules are covered by tests/test_rank.py (issue #36).
"""

from datetime import date

import pytest

from insidejob.config import ConfigError, _rank
from insidejob.rank import DEFAULT_RANK, score, years_of_experience
from tests.helpers import make_job

TODAY = date(2026, 11, 18)


@pytest.mark.parametrize(
    ("text", "years"),
    [
        ("You have 3+ years of experience in Python", 3),
        ("2-4 years of relevant work experience", 2),
        ("at least 5 years' experience with React", 5),
        ("Minimum 2 years experience", 2),
        ("Vähintään 3 vuoden kokemus ohjelmistokehityksestä", 3),
        ("2-3 vuotta työkokemusta", 2),
        ("We have 20 years of history and a great culture", 0),
        ("No prior experience needed", 0),
        ("1 year of studies left", 0),
    ],
)
def test_years_of_experience(text, years):
    assert years_of_experience(text) == years


def test_experience_penalty_is_a_reason():
    job = make_job(title="Junior Developer", description="Requires 3+ years of experience.")
    rank = score(job, DEFAULT_RANK, TODAY)
    assert "asks 3+ yrs -2" in rank.reasons


def test_one_year_is_not_penalised():
    job = make_job(description="1 year of experience with Git is a plus.")
    assert not any(r.startswith("asks") for r in score(job, DEFAULT_RANK, TODAY).reasons)


def test_ai_in_the_description_does_not_count():
    job = make_job(description="We build AI agents with LLMs. AI everywhere.")
    assert not any("AI" in r for r in score(job, DEFAULT_RANK, TODAY).reasons)


def test_ai_in_the_title_counts():
    job = make_job(title="AI Summer Trainee", description="We use AI agents.")
    assert "AI +3" in score(job, DEFAULT_RANK, TODAY).reasons


def test_other_interests_still_count_from_the_description():
    job = make_job(description="You will work with OpenGL shaders.")
    assert "OpenGL, shaders +1.5" in score(job, DEFAULT_RANK, TODAY).reasons


def test_config_keys():
    rule = {"points": 3, "match": "ai", "label": "AI", "title_only": True}
    config = _rank({"experience": {"min_years": 3, "points": -1}, "interests": [rule]})
    assert (config.experience_years, config.experience_points) == (3, -1)
    assert config.interests[0].title_only


@pytest.mark.parametrize(
    "raw",
    [
        {"experience": {"years": 3}},
        {"experience": {"points": "x"}},
        {"interests": [{"points": 3, "match": "ai", "title_only": "yes"}]},
    ],
)
def test_bad_config_fails(raw):
    with pytest.raises(ConfigError):
        _rank(raw)
