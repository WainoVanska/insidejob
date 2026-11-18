"""Order new jobs best first with a simple, explainable points score.

Ranking never hides anything: the filters decide what is relevant, ranking only decides
the order and adds stars plus a short "why" line. Every signal is a list of rules, and
the first rule that matches wins (except interests, where the best-scoring tier wins).
All of it can be tuned in `config.yaml` under `rank:`; `DEFAULT_RANK` is used otherwise.

    title      intern/trainee/summer > junior > graduate
    location   capital region > rest of Finland > remote/EU (unknown location gets its own value)
    interests  best tier found; half points if it's only in the description, not the title
    start      e.g. "summer 2027"
    deadline   closer deadline = more points
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from insidejob.models import Job


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


@dataclass(frozen=True)
class Rule:
    """`points` if `match` is found. `label` names the rule in the reason line."""

    points: float
    match: re.Pattern[str]
    label: str = ""


@dataclass(frozen=True)
class DeadlineRule:
    within_days: int
    points: float


@dataclass(frozen=True)
class RankConfig:
    title: tuple[Rule, ...]
    location: tuple[Rule, ...]
    unknown_location: float
    interests: tuple[Rule, ...]
    start: tuple[Rule, ...]
    deadline: tuple[DeadlineRule, ...]
    three_stars: float = 10
    two_stars: float = 6


@dataclass(frozen=True)
class Rank:
    score: float
    stars: int
    reasons: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class RankedJob:
    job: Job
    rank: Rank


# "C++" can't use \b (it ends in non-word characters), so it gets a lookbehind instead.
_INTEREST_SOFTWARE = (
    r"(?<!\w)c\+\+"
    r"|\b(software|developers?|engineers?|python|scala|backend|full-?stack|embedded|systems?)\b"
)

DEFAULT_RANK = RankConfig(
    title=(
        Rule(
            3,
            _rx(
                r"\b(interns?|internships?|trainees?|traineeship|summer|thesis|launchpad)\b"
                r"|kesä|harjoittel|opinnäyte|diplomityö"
            ),
            "intern",
        ),
        Rule(2, _rx(r"\bjunior\b"), "junior"),
        Rule(1, _rx(r"\bgraduates?\b"), "graduate"),
    ),
    location=(
        Rule(3, _rx(r"helsinki|espoo|vantaa")),
        Rule(2, _rx(r"finland|suomi")),
        Rule(1, _rx(r"\bremote\b|\b(eu|europe|emea)\b")),
    ),
    unknown_location=1,
    interests=(
        Rule(
            3,
            _rx(
                r"\b(graphics|rendering|renderer|opengl|vulkan|directx|shaders?|glsl|gpus?|cuda"
                r"|game engines?|3d|real-time|xr|vr|ar|mixed reality|computer vision)\b"
            ),
            "graphics",
        ),
        Rule(
            3,
            _rx(
                r"\b(llms?|agents?|agentic|ai|genai|generative|automation|mcp|prompt\w*|ai tools)\b"
            ),
            "AI",
        ),
        Rule(
            2,
            _rx(
                r"\b(games?|gameplay|unity|unreal|ui|ux|front-?end|react|typescript|web|mobile"
                r"|apps?)\b"
            ),
            "apps & games",
        ),
        Rule(1, _rx(_INTEREST_SOFTWARE), "software"),
        Rule(
            0,
            _rx(r"\b(data|analytics|machine learning|ml|cloud|devops|platform|infrastructure)\b"),
            "data & cloud",
        ),
    ),
    start=(Rule(2, _rx(r"summer 2027|kesä 2027|\b(may|jun|jul|aug)\w* 2027"), "summer 2027"),),
    deadline=(DeadlineRule(14, 2), DeadlineRule(30, 1)),
)

MAX_KEYWORDS = 3


def score(job: Job, config: RankConfig, today: date) -> Rank:
    points = 0.0
    reasons: list[str] = []

    if rule := _first(config.title, job.title):
        points += rule.points
        reasons.append(rule.label)

    if job.location:
        for rule in config.location:
            if m := rule.match.search(job.location):
                points += rule.points
                reasons.append(rule.label or m.group(0).title())
                break
    else:
        points += config.unknown_location

    interest, keywords = _best_interest(job, config.interests)
    points += interest
    if keywords:
        reasons.append(", ".join(keywords))

    start_text = f"{job.start or ''}\n{job.title}"
    if rule := _first(config.start, start_text):
        points += rule.points
        reasons.append(rule.label or "start")

    if job.deadline:
        days = (job.deadline - today).days
        for deadline in sorted(config.deadline, key=lambda d: d.within_days):
            if 0 <= days <= deadline.within_days:
                points += deadline.points
                reasons.append("closes today" if days == 0 else f"closes in {days} d")
                break

    return Rank(points, _stars(points, config), tuple(r for r in reasons if r))


def rank_jobs(jobs: list[Job], config: RankConfig, today: date) -> list[RankedJob]:
    """Best first. Ties: the closer deadline first, then the newest posting."""
    ranked = [RankedJob(job, score(job, config, today)) for job in jobs]
    return sorted(ranked, key=_sort_key)


def stars_text(stars: int) -> str:
    return "★" * stars


def _first(rules: tuple[Rule, ...], text: str) -> Rule | None:
    return next((rule for rule in rules if rule.match.search(text)), None)


def _best_interest(job: Job, rules: tuple[Rule, ...]) -> tuple[float, list[str]]:
    """Points of the best tier (full in the title, half in the description) and its keywords."""
    best_points, best_keywords = 0.0, []
    for rule in rules:
        in_title = _keywords(rule.match, job.title)
        in_body = _keywords(rule.match, job.description)
        if not in_title and not in_body:
            continue
        points = rule.points if in_title else rule.points / 2
        if points > best_points:
            best_points = points
            best_keywords = _unique(in_title + in_body)[:MAX_KEYWORDS]
    return best_points, best_keywords


def _keywords(pattern: re.Pattern[str], text: str) -> list[str]:
    return [m.group(0) for m in pattern.finditer(text)]


def _unique(words: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for word in words:
        if word.lower() not in seen:
            seen.add(word.lower())
            out.append(word)
    return out


def _stars(points: float, config: RankConfig) -> int:
    if points >= config.three_stars:
        return 3
    if points >= config.two_stars:
        return 2
    return 1


def _sort_key(item: RankedJob) -> tuple:
    job = item.job
    deadline = job.deadline.toordinal() if job.deadline else float("inf")
    posted = -job.posted_at.timestamp() if isinstance(job.posted_at, datetime) else float("inf")
    return (-item.rank.score, deadline, posted)
