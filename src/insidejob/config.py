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

All regexes are case-insensitive. Problems raise `ConfigError` with a message that
points at the offending entry, so a bad config fails fast instead of silently matching
nothing.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from insidejob.adapters import ADAPTERS

FILTER_KEYS = ("title", "exclude", "location")


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
    return Config(sources=sources)


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
