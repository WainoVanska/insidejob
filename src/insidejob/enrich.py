"""Fill in job details the source didn't list, using simple EN + FI regex heuristics.

Only empty fields are filled, and every filled field is named in `Job.inferred` so the
alert can mark it with `~`. No signal means the field stays unknown: we never guess
blindly. The title (and location) is checked before the description, because it's
the most specific text we have.

This module is deliberately small and table-driven, so it can later be replaced by an
LLM without touching the adapters or the pipeline.
"""

import dataclasses
import re
from typing import TypeVar

from insidejob.models import Employment, Job, Workplace

T = TypeVar("T")


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# First match wins, so order matters: e.g. "hybrid" text often also says "on-site".
WORKPLACE_RULES: list[tuple[Workplace, re.Pattern[str]]] = [
    (
        Workplace.HYBRID,
        _rx(r"\bhybrid|hybridi|\bdays? (a|per) week (in|at) (the )?office|lähipäiv"),
    ),
    (
        Workplace.REMOTE,
        _rx(
            r"\bfully remote|100\s?% remote|\bremote[- ](role|position|job|work|first)\b"
            r"|\bwork(ing)? (fully )?remotely|^remote\b|\bremote\s*[-–(,]|\bremote$"
            r"|täysin etä|\betätyö"
        ),
    ),
    (
        Workplace.ONSITE,
        _rx(r"\bon-?site\b|\bin-office\b|\bat (our|the) office\b|lähityö|toimistolla"),
    ),
]

EMPLOYMENT_RULES: list[tuple[Employment, re.Pattern[str]]] = [
    (
        Employment.INTERNSHIP,
        _rx(
            r"\b(interns?|internships?|trainees?|traineeship|summer job|thesis|working student"
            r"|apprentice(ship)?)\b|harjoittel|kesätyö|opinnäyte|diplomityö"
        ),
    ),
    (Employment.PART_TIME, _rx(r"\bpart[- ]time\b|osa-aika")),
    (
        Employment.FIXED_TERM,
        _rx(
            r"\bfixed[- ]term\b|\bFTC\b|\btemporary\b|määräaikai"
            r"|\b\d+[- ]months? (contract|position|role)\b"
        ),
    ),
    (Employment.FULL_TIME, _rx(r"\bfull[- ]time\b|kokoaika|\bpermanent\b|vakituinen")),
]

_MONTHS_EN = {
    "jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr", "may": "May", "jun": "Jun",
    "jul": "Jul", "aug": "Aug", "sep": "Sep", "oct": "Oct", "nov": "Nov", "dec": "Dec",
}  # fmt: skip
_MONTHS_FI = {
    "tammi": "Jan", "helmi": "Feb", "maalis": "Mar", "huhti": "Apr", "touko": "May",
    "kesä": "Jun", "heinä": "Jul", "elo": "Aug", "syys": "Sep", "loka": "Oct",
    "marras": "Nov", "joulu": "Dec",
}  # fmt: skip

_EN_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_FI_MONTH = r"(tammi|helmi|maalis|huhti|touko|kesä|heinä|elo|syys|loka|marras|joulu)kuu\w*"
_YEAR = r"(20\d\d)"

_START_SEASON = _rx(r"\b(summer|kesä(?:llä|n)?)\s+(?:of\s+)?" + _YEAR + r"\b")
_START_EN = _rx(
    r"\b(?:start(?:ing|s)?|begin(?:ning|s)?|commenc\w*|from)\b[^.\n]{0,30}?\b"
    + _EN_MONTH
    + r"(?:\s+\d{1,2}(?:st|nd|rd|th)?,?)?(?:\s+"
    + _YEAR
    + r")?\b"
)
_START_FI = _rx(_FI_MONTH + r"(?:sta|n)?\s*(?:" + _YEAR + r"\s*)?(?:alkaen|aloitus|alkava)")
_START_ASAP = _rx(r"\b(asap|as soon as possible)\b|\bheti\b|mahdollisimman pian")


def enrich(job: Job) -> Job:
    head = f"{job.title}\n{job.location}"
    updates: dict[str, object] = {}

    if job.workplace is None:
        found = _first_rule(WORKPLACE_RULES, head, job.description)
        if found:
            updates["workplace"] = found
    if job.employment is None:
        found = _first_rule(EMPLOYMENT_RULES, job.title, job.description)
        if found:
            updates["employment"] = found
    if job.start is None:
        found = _start(job.title) or _start(job.description)
        if found:
            updates["start"] = found

    if not updates:
        return job
    return dataclasses.replace(job, **updates, inferred=job.inferred | set(updates))


def _first_rule(rules: list[tuple[T, re.Pattern[str]]], *texts: str) -> T | None:
    for text in texts:
        for value, pattern in rules:
            if pattern.search(text):
                return value
    return None


def _start(text: str) -> str | None:
    if m := _START_SEASON.search(text):
        return f"summer {m.group(2)}"
    if m := _START_FI.search(text):
        return _label(_MONTHS_FI[m.group(1).lower()], m.group(2))
    if m := _START_EN.search(text):
        return _label(_MONTHS_EN[m.group(1).lower()[:3]], m.group(2))
    if _START_ASAP.search(text):
        return "asap"
    return None


def _label(month: str, year: str | None) -> str:
    return f"{month} {year}" if year else month
