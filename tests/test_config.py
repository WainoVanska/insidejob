from pathlib import Path

import pytest

from insidejob.config import ConfigError, load_config, parse_config

ROOT = Path(__file__).parent.parent


def minimal(**overrides):
    data = {
        "filters": {"title": "intern", "exclude": "senior", "location": "helsinki"},
        "sources": [{"company": "RELEX", "type": "greenhouse", "board": "relex"}],
    }
    return data | overrides


def test_loads_repo_config():
    config = load_config(ROOT / "config.yaml")
    assert len(config.sources) >= 9
    known = {"greenhouse", "rss", "ashby", "workday", "workable"}
    assert {source.type for source in config.sources} <= known


def test_loads_example_config():
    config = load_config(ROOT / "config.example.yaml")
    assert [s.board for s in config.sources] == ["relex", "wolt"]


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
