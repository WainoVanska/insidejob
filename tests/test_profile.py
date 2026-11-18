"""`looking_for:` -> filters and ranking. Checked through parse_config, so the generated
config also goes through the normal validation."""

from datetime import date

import pytest

from insidejob.config import ConfigError, parse_config
from insidejob.filters import matches
from insidejob.rank import score
from tests.helpers import make_job

TODAY = date(2026, 11, 18)
COMPANIES = ["https://job-boards.greenhouse.io/acme"]


def config(**looking_for):
    return parse_config({"looking_for": looking_for, "companies": COMPANIES})


def passes(cfg, **job):
    (source,) = cfg.sources
    return matches(make_job(**job), source.filters)


def test_roles_default_to_all_and_seniors_are_out():
    cfg = config()
    for title in ("Summer Trainee", "Thesis worker", "Junior Developer", "Graduate Engineer"):
        assert passes(cfg, title=title), title
    assert passes(cfg, title="Kesätyöntekijä")
    assert not passes(cfg, title="Senior Developer")
    assert not passes(cfg, title="Junior Product Manager")
    assert not passes(cfg, title="Software Engineer")


def test_roles_narrow_the_title_filter_and_the_title_points():
    cfg = config(roles=["junior", "intern"])
    assert passes(cfg, title="Junior Developer")
    assert not passes(cfg, title="Graduate Engineer")
    assert [(r.label, r.points) for r in cfg.rank.title] == [("intern", 3), ("junior", 2)]


def test_title_points_and_max_score():
    cfg = config(
        cities=["Helsinki"], country="Finland", interests=["graphics"], start="summer 2027"
    )
    assert [(r.label, r.points) for r in cfg.rank.title] == [
        ("intern", 3),
        ("thesis", 3),
        ("junior", 2),
        ("graduate", 1),
    ]
    rank = score(make_job(title="Junior Developer"), cfg.rank, TODAY)
    assert rank.out_of == 13  # title 3 + location 3 + interests 3 + start 2 + deadline 2


def test_no_places_means_no_location_filter():
    cfg = config()
    assert passes(cfg, location="San Francisco")
    assert cfg.rank.location == ()
    assert cfg.rank.unknown_location == 0


def test_cities_country_and_remote():
    cfg = config(cities=["Helsinki", "Espoo"], country="Finland", remote=True)
    assert passes(cfg, location="Espoo")
    assert passes(cfg, location="Tampere, Suomi")  # country alias
    assert passes(cfg, location="Remote - EMEA")
    assert not passes(cfg, location="Remote - United States")
    assert not passes(cfg, location="Stockholm, Sweden")

    def points(location):
        return score(make_job(title="Trainee", location=location), cfg.rank, TODAY).score

    assert points("Helsinki") == 3 + 3
    assert points("Oulu, Finland") == 3 + 2
    assert points("Remote, Europe") == 3 + 1
    assert points("") == 3 + 2  # unknown location with a country: probably local


def test_remote_anywhere_lets_every_remote_job_in():
    cfg = config(country="Finland", remote="anywhere")
    assert passes(cfg, location="Remote - United States")
    assert not passes(cfg, location="Berlin, Germany")


@pytest.mark.parametrize(
    ("looking_for", "unknown"),
    [({"country": "Finland"}, 2), ({"cities": ["Oulu"]}, 1), ({}, 0)],
)
def test_unknown_location_points(looking_for, unknown):
    assert config(**looking_for).rank.unknown_location == unknown


def test_unknown_country_is_used_as_written():
    cfg = config(country="Narnia")
    assert passes(cfg, location="Cair Paravel, Narnia")


def test_interest_synonyms_title_full_description_half():
    cfg = config(interests=["graphics"])
    rank = score(make_job(title="Rendering Trainee"), cfg.rank, TODAY)
    assert "Rendering +3" in rank.reasons
    rank = score(make_job(title="Trainee", description="We write Vulkan shaders."), cfg.rank, TODAY)
    assert "Vulkan, shaders +1.5" in rank.reasons


def test_boilerplate_words_count_in_the_title_only():
    cfg = config(interests=["AI"])
    boilerplate = make_job(title="Trainee", description="We use AI everywhere.")
    assert score(boilerplate, cfg.rank, TODAY).reasons == ("intern +3",)
    specific = make_job(title="Trainee", description="You will fine-tune LLMs.")
    assert "LLMs +1.5" in score(specific, cfg.rank, TODAY).reasons
    assert "AI +3" in score(make_job(title="AI Trainee"), cfg.rank, TODAY).reasons


def test_unknown_interest_is_used_as_written_and_boilerplate_still_applies():
    cfg = config(interests=["Rust", "agile"])
    (rust, agile) = cfg.rank.interests
    assert (rust.label, rust.title_only) == ("Rust", False)
    assert (agile.label, agile.title_only) == ("agile", True)
    assert rust.match.search("Rust Developer")


@pytest.mark.parametrize(
    ("start", "hits", "misses"),
    [
        (
            "summer 2027",
            ["summer 2027", "Jun 2027", "kesä 2027", "Aug 2027", "elokuu 2027"],
            ["summer 2026", "Sep 2027", "Marketing Trainee"],
        ),
        ("kesä 2027", ["summer 2027", "Jul 2027"], ["Oct 2027"]),
        ("June 2027", ["Jun 2027", "kesäkuu 2027"], ["Jul 2027", "summer 2027"]),
        ("autumn 2027", ["Sep 2027", "syksy 2027", "Nov 2027"], ["Aug 2027"]),
        ("summer", ["summer 2027", "Jun"], ["Sep"]),
    ],
)
def test_start_expands_seasons_and_months(start, hits, misses):
    (rule,) = config(start=start).rank.start
    assert rule.points == 2
    for text in hits:
        assert rule.match.search(text), text
    for text in misses:
        assert not rule.match.search(text), text


def test_explicit_filters_and_rank_keys_replace_generated_ones():
    cfg = parse_config(
        {
            "looking_for": {"cities": ["Helsinki"], "interests": ["games"]},
            "filters": {"location": "tampere"},
            "rank": {"interests": [{"points": 1, "words": ["Rust"]}]},
            "companies": COMPANIES,
        }
    )
    (source,) = cfg.sources
    assert source.filters.location.pattern == "tampere"
    assert source.filters.exclude is not None  # still generated
    assert [r.points for r in cfg.rank.interests] == [1]
    assert cfg.rank.location[0].match.search("Helsinki")  # still generated


@pytest.mark.parametrize(
    ("looking_for", "message"),
    [
        ([], "must be a mapping"),
        ({"roles": ["ceo"]}, "roles: unknown"),
        ({"remote": "maybe"}, "remote must be"),
        ({"start": "soon"}, "isn't a season or month"),
        ({"start": "2027"}, "can't read"),
        ({"cities": 5}, "cities must be a list"),
        ({"salary": 1}, "unknown key"),
    ],
)
def test_bad_looking_for_fails_in_plain_words(looking_for, message):
    with pytest.raises(ConfigError, match=f"looking_for: .*{message}"):
        parse_config({"looking_for": looking_for, "companies": COMPANIES})
