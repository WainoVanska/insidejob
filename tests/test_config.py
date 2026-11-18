from pathlib import Path

import pytest

from insidejob.config import ConfigError, _rank, load_config, parse_config
from insidejob.rank import DEFAULT_RANK

ROOT = Path(__file__).parent.parent


def minimal(**overrides):
    data = {
        "filters": {"title": "intern", "exclude": "senior", "location": "helsinki"},
        "sources": [{"company": "RELEX", "type": "greenhouse", "board": "relex"}],
    }
    return data | overrides


def test_loads_starter_config_with_neutral_ranking():
    config = load_config(ROOT / "config.yaml")
    assert len(config.sources) >= 5
    known = {"greenhouse", "rss", "ashby", "workday", "workable"}
    assert {source.type for source in config.sources} <= known
    assert config.rank == DEFAULT_RANK  # no personal preferences in the starter


def test_loads_example_config():
    config = load_config(ROOT / "config.example.yaml")
    assert [s.board for s in config.sources][:2] == ["wolt", "supercell"]
    assert config.sources[-1].filters.location.pattern == "helsinki"  # per-source override
    assert config.rank.interests[1].title_only  # AI: title only
    assert (config.rank.green_at, config.rank.yellow_at) == (0.65, 0.4)


def test_words_match_whole_words_in_any_case():
    (rule,) = _rank(
        {"location": [{"points": 3, "words": ["Helsinki", "C++", "entry level"]}]}
    ).location
    assert rule.match.search("HELSINKI, Finland")
    assert rule.match.search("Senior C++ dev")
    assert rule.match.search("Entry  Level role")
    assert not rule.match.search("Helsinkiläinen")


def test_ai_word_does_not_match_inside_other_words():
    (rule,) = _rank({"interests": [{"points": 3, "words": ["AI"]}]}).interests
    assert rule.match.search("AI engineer")
    assert not rule.match.search("maintain the platform")


@pytest.mark.parametrize(
    "rule",
    [
        {"points": 3},  # neither words nor match
        {"points": 3, "words": ["a"], "match": "a"},  # both
        {"points": 3, "words": []},
        {"points": 3, "words": [1, 2]},
    ],
)
def test_rule_needs_exactly_one_of_words_or_match(rule):
    with pytest.raises(ConfigError):
        _rank({"location": [rule]})


def test_levels_are_shares_of_the_best_score():
    config = _rank({"levels": {"green": 0.8, "yellow": 0.5}})
    assert (config.green_at, config.yellow_at) == (0.8, 0.5)


@pytest.mark.parametrize("levels", [{"green": 0.3, "yellow": 0.5}, {"green": 9}, {"blue": 1}])
def test_bad_levels_fail(levels):
    with pytest.raises(ConfigError):
        _rank({"levels": levels})


def test_old_stars_key_explains_the_new_one():
    with pytest.raises(ConfigError, match="levels"):
        _rank({"stars": {"three": 9, "two": 6}})


def test_source_key_matches_job_source():
    (source,) = parse_config(minimal()).sources
    assert source.key == "greenhouse:relex"


def test_global_filters_apply_to_every_source():
    (source,) = parse_config(minimal()).sources
    assert source.filters.title.pattern == "intern"
    assert source.filters.location.pattern == "helsinki"


def test_regexes_are_case_insensitive():
    (source,) = parse_config(minimal()).sources
    assert source.filters.title.search("Summer INTERN")


def test_source_filter_replaces_only_that_key():
    data = minimal()
    data["sources"][0]["filters"] = {"location": "espoo"}
    (source,) = parse_config(data).sources
    assert source.filters.location.pattern == "espoo"
    assert source.filters.title.pattern == "intern"  # still the global one
    assert source.filters.exclude.pattern == "senior"


def test_optional_filters_may_be_omitted():
    (source,) = parse_config(minimal(filters={"title": "intern"})).sources
    assert source.filters.exclude is None
    assert source.filters.location is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "must be a mapping"),
        (minimal(filters={}), "filters.title is required"),
        (minimal(filters={"title": "("}), "invalid regex"),
        (minimal(filters={"title": "x", "salary": "1"}), "unknown filter key"),
        (minimal(sources=[]), "non-empty list"),
        (minimal(sources=[{"company": "A", "type": "greenhouse"}]), "`board` is required"),
        (minimal(sources=[{"type": "greenhouse", "board": "a"}]), "`company` is required"),
        (minimal(sources=[{"company": "A", "type": "taleo", "board": "a"}]), "unknown type"),
        (
            minimal(sources=[{"company": "A", "type": "greenhouse", "board": "a", "filters": 3}]),
            "must be a mapping",
        ),
        (
            minimal(
                sources=[
                    {"company": "A", "type": "greenhouse", "board": "a"},
                    {"company": "B", "type": "greenhouse", "board": "a"},
                ]
            ),
            "duplicate source greenhouse:a",
        ),
    ],
)
def test_invalid_config_fails_fast(data, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(data)


WORKDAY = {"company": "KONE", "type": "workday", "board": "kone.wd3.myworkdayjobs.com/Careers"}


def test_options_are_passed_through():
    data = minimal(sources=[WORKDAY | {"options": {"facet": " Finland "}}])
    (source,) = parse_config(data).sources
    assert source.options == {"facet": "Finland"}


def test_options_default_to_empty():
    (source,) = parse_config(minimal()).sources
    assert source.options == {}


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (WORKDAY, "`facet` is required for type workday"),
        (WORKDAY | {"options": {"facet": "Finland", "x": "1"}}, r"unknown option\(s\) \['x'\]"),
        (WORKDAY | {"options": {"facet": 3}}, "must be a non-empty string"),
        (
            {"company": "A", "type": "greenhouse", "board": "a", "options": {"facet": "x"}},
            "unknown option",
        ),
    ],
)
def test_invalid_options(source, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(minimal(sources=[source]))


def test_error_names_the_source(tmp_path):
    data = minimal(sources=[{"company": "A", "type": "greenhouse", "board": "a"}, {"company": "B"}])
    with pytest.raises(ConfigError, match=r"sources\[1\]"):
        parse_config(data)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="cannot read config"):
        load_config(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("filters: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(path)
