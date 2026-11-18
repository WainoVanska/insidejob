"""The normalized job record every adapter produces."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class Workplace(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class Employment(StrEnum):
    FULL_TIME = "full-time"
    PART_TIME = "part-time"
    INTERNSHIP = "internship"
    FIXED_TERM = "fixed-term"


@dataclass(frozen=True)
class Job:
    """One job posting, normalized across sources.

    `id` is globally unique: `<source>:<job id in that source>`, where `source` is
    `<adapter type>:<board>` (e.g. `greenhouse:relex`), which is also the state key.

    The optional detail fields hold what the source *lists*. `enrich` may fill gaps
    later, and records the names of the fields it guessed in `inferred`.
    """

    id: str
    source: str
    company: str
    title: str
    location: str
    url: str
    posted_at: datetime | None = None
    workplace: Workplace | None = None
    employment: Employment | None = None
    start: str | None = None
    deadline: date | None = None
    inferred: frozenset[str] = frozenset()
    # Plain text, kept in memory for enrich (and later scoring). Never stored in state.
    description: str = field(default="", compare=False, repr=False)
