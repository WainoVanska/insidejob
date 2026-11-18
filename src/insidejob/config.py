"""Load and validate `config.yaml`.

Shape:

    filters:                      # global defaults
      title: "<regex>"            # required: job title must match
      exclude: "<regex>"          # optional: job title must NOT match
      location: "<regex>"         # optional: location must match (empty location passes)
    sources:
      - company: RELEX Solutions
        type: greenhouse
        board: relex
        filters:                  # optional: each key given here REPLACES the global one
          location: "..."
        options:                  # optional: adapter-specific settings (see each adapter's OPTIONS)
          facet: Finland
    rank:                         # optional: how new jobs are ordered (defaults: rank.DEFAULT_RANK)
      title: [{points: 3, match: "intern|trainee", label: intern}, ...]
      location: [...]             # same rule shape; first match wins
      interests: [...]            # best tier wins; half points if only in the description;
                                  # a rule with `title_only: true` ignores the description
      start: [...]
      unknown_location: 2
      deadline: [{within_days: 14, points: 2}, ...]
      stars: {three: 9, two: 6}
      experience: {min_years: 2, points: -2}   # asks for 2+ years of experience

All regexes are case-insensitive. Problems raise `ConfigError` with a message that
points at the offending entry, so a bad config fails fast instead of silently matching
nothing.
"""

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from insidejob.adapters import ADAPTERS
from insidejob.rank import DEFAULT_RANK, DeadlineRule, RankConfig, Rule

FILTER_KEYS = ("title", "exclude", "location")
RANK_RULE_KEYS = ("title", "location", "interests", "start")
RANK_KEYS = (*RANK_RULE_KEYS, "unknown_location", "deadline", "stars", "experience")


class ConfigError(ValueError):
    """The config file is missing, unreadable or invalid."""


@dataclass(frozen=True)
class Filters:
    title: re.Pattern[str]
    exclude: re.Pattern[str] | None = None
    location: re.Pattern[str] | None = None


@dataclass(frozen=True)
class Source:
    company: str
    type: str
    board: str
    filters: Filters
    options: dict[str, str] = field(default_factory=dict, hash=False)

    @property
    def key(self) -> str:
        """`<type>:<board>`, the same value as `Job.source` and the state key."""
        return f"{self.type}:{self.board}"


@dataclass(frozen=True)
class Config:
    sources: list[Source]
    rank: RankConfig = DEFAULT_RANK


def load_config(path: Path) -> Config:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    return parse_config(data)


def parse_config(data: Any) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("config must be a mapping with `filters` and `sources`")

    global_raw = _mapping(data.get("filters"), "filters")
    if "title" not in global_raw:
        raise ConfigError("filters.title is required")
    _filters(global_raw, "filters")  # validate the globals even if every source overrides them

    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ConfigError("sources must be a non-empty list")

    sources: list[Source] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_sources):
        source = _source(raw, f"sources[{i}]", global_raw)
        if source.key in seen:
            raise ConfigError(f"sources[{i}]: duplicate source {source.key}")
        seen.add(source.key)
        sources.append(source)
    return Config(sources=sources, rank=_rank(data.get("rank")))


def _rank(value: Any) -> RankConfig:
    """`rank:` is optional; each key given replaces that part of DEFAULT_RANK."""
    raw = _mapping(value, "rank")
    unknown = set(raw) - set(RANK_KEYS)
    if unknown:
        raise ConfigError(
            f"rank: unknown key(s) {sorted(unknown)} (allowed: {', '.join(RANK_KEYS)})"
        )

    parts: dict[str, Any] = {}
    for key in RANK_RULE_KEYS:
        if key in raw:
            parts[key] = _rules(raw[key], f"rank.{key}")
    if "unknown_location" in raw:
        parts["unknown_location"] = _number(raw["unknown_location"], "rank.unknown_location")
    if "deadline" in raw:
        parts["deadline"] = _deadlines(raw["deadline"], "rank.deadline")
    if "stars" in raw:
        stars = _mapping(raw["stars"], "rank.stars")
        if set(stars) - {"three", "two"}:
            raise ConfigError("rank.stars: only `three` and `two` thresholds are allowed")
        if "three" in stars:
            parts["three_stars"] = _number(stars["three"], "rank.stars.three")
        if "two" in stars:
            parts["two_stars"] = _number(stars["two"], "rank.stars.two")
    if "experience" in raw:
        experience = _mapping(raw["experience"], "rank.experience")
        if set(experience) - {"min_years", "points"}:
            raise ConfigError("rank.experience: only `min_years` and `points` are allowed")
        if "min_years" in experience:
            years = _number(experience["min_years"], "rank.experience.min_years")
            parts["experience_years"] = int(years)
        if "points" in experience:
            parts["experience_points"] = _number(experience["points"], "rank.experience.points")

    return replace(DEFAULT_RANK, **parts)


def _rules(value: Any, where: str) -> tuple[Rule, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{where} must be a list of {{points, match, label}}")
    rules = []
    for i, item in enumerate(value):
        item = _mapping(item, f"{where}[{i}]")
        if set(item) - {"points", "match", "label", "title_only"}:
            raise ConfigError(
                f"{where}[{i}]: only `points`, `match`, `label` and `title_only` are allowed"
            )
        pattern = _regex(item.get("match"), f"{where}[{i}].match", required=True)
        label = item.get("label", "")
        if not isinstance(label, str):
            raise ConfigError(f"{where}[{i}].label must be a string")
        title_only = item.get("title_only", False)
        if not isinstance(title_only, bool):
            raise ConfigError(f"{where}[{i}].title_only must be true or false")
        points = _number(item.get("points"), f"{where}[{i}].points")
        rules.append(Rule(points, pattern, label, title_only))
    return tuple(rules)


def _deadlines(value: Any, where: str) -> tuple[DeadlineRule, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{where} must be a list of {{within_days, points}}")
    rules = []
    for i, item in enumerate(value):
        item = _mapping(item, f"{where}[{i}]")
        days = item.get("within_days")
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            raise ConfigError(f"{where}[{i}].within_days must be a whole number of days")
        rules.append(DeadlineRule(days, _number(item.get("points"), f"{where}[{i}].points")))
    return tuple(rules)


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{where} must be a number")
    return float(value)


def _source(raw: Any, where: str, global_raw: dict[str, Any]) -> Source:
    raw = _mapping(raw, where)
    for name in ("company", "type", "board"):
        if not isinstance(raw.get(name), str) or not raw[name].strip():
            raise ConfigError(f"{where}: `{name}` is required")
    if raw["type"] not in ADAPTERS:
        known = ", ".join(sorted(ADAPTERS))
        raise ConfigError(f"{where}: unknown type {raw['type']!r} (known: {known})")

    overrides = _mapping(raw.get("filters"), f"{where}.filters")
    merged = global_raw | overrides  # per key: the source's value replaces the global one
    return Source(
        company=raw["company"].strip(),
        type=raw["type"],
        board=raw["board"].strip(),
        filters=_filters(merged, f"{where}.filters"),
        options=_options(raw.get("options"), raw["type"], f"{where}.options"),
    )


def _options(value: Any, adapter_type: str, where: str) -> dict[str, str]:
    """Check options against the adapter's OPTIONS: {name: required}."""
    raw = _mapping(value, where)
    allowed = getattr(ADAPTERS[adapter_type], "OPTIONS", {})
    unknown = set(raw) - set(allowed)
    if unknown:
        hint = f" (allowed: {', '.join(sorted(allowed))})" if allowed else ""
        raise ConfigError(f"{where}: unknown option(s) {sorted(unknown)} for {adapter_type}{hint}")
    for name, required in allowed.items():
        if required and name not in raw:
            raise ConfigError(f"{where}: `{name}` is required for type {adapter_type}")
    options: dict[str, str] = {}
    for name, val in raw.items():
        if not isinstance(val, str) or not val.strip():
            raise ConfigError(f"{where}.{name} must be a non-empty string")
        options[name] = val.strip()
    return options


def _filters(raw: dict[str, Any], where: str) -> Filters:
    unknown = set(raw) - set(FILTER_KEYS)
    if unknown:
        raise ConfigError(f"{where}: unknown filter key(s) {sorted(unknown)}")
    return Filters(
        title=_regex(raw.get("title"), f"{where}.title", required=True),
        exclude=_regex(raw.get("exclude"), f"{where}.exclude"),
        location=_regex(raw.get("location"), f"{where}.location"),
    )


def _regex(value: Any, where: str, *, required: bool = False) -> re.Pattern[str] | None:
    if value is None or value == "":
        if required:
            raise ConfigError(f"{where} is required")
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{where} must be a string (a regex)")
    try:
        return re.compile(value, re.IGNORECASE)
    except re.error as exc:
        raise ConfigError(f"{where}: invalid regex {value!r}: {exc}") from exc


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping")
    return value
