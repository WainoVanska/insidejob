"""Order new jobs best first with a simple, explainable points score.

Ranking never hides anything: the filters decide what is relevant, ranking only decides
the order and adds a match level (1-3) plus a "why" line where each reason shows its
points, so the reasons add up to the score. Every signal is a list of rules, and
the first rule that matches wins (except interests, where the best-scoring tier wins).
All of it can be tuned in `config.yaml` under `rank:`; `DEFAULT_RANK` is used otherwise.

    title      intern/trainee/summer > junior > graduate
    location   capital region > rest of Finland > remote/EU (unknown location gets its own value)
    interests  best tier found; half points if it's only in the description, not the title.
               The AI tier counts from the title only: nearly every description repeats
               "AI" as company boilerplate, so it said nothing about the job itself.
    start      e.g. "summer 2027"
    deadline   closer deadline = more points
    experience minus points if the text asks for 2+ years of experience
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from insidejob.models import Job


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


@dataclass(frozen=True)
class Rule:
    """`points` if `match` is found. `label` names the rule in the reason line.

    `title_only` (interests): ignore the description for this rule.
    """

    points: float
    match: re.Pattern[str]
    label: str = ""
    title_only: bool = False


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
    three_stars: float = 9
    two_stars: float = 6
    # A job asking for this many years of experience or more gets `experience_points`.
    experience_years: int = 2
    experience_points: float = -2


@dataclass(frozen=True)
class Rank:
    score: float
    stars: int  # match level: 3 strong (green), 2 some (yellow), 1 weak (red)
    reasons: tuple[str, ...] = field(default=())
    out_of: float = 0  # best score possible with this config; 0 = not known
    places: tuple[str, ...] = ()  # the job's locations, most relevant first


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
    # Every watched company is Finnish, so a job without a location is most likely in
    # Finland: score it like "rest of Finland" rather than like remote.
    unknown_location=2,
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
            title_only=True,
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

# "3+ years of experience", "2-4 years of relevant work experience", "5 years' experience",
# Finnish "3 vuoden kokemus" / "2-3 vuotta työkokemusta". Group 1 = the (lower) number.
_EXPERIENCE = (
    _rx(
        r"\b(\d{1,2})\s*(?:\+|(?:-|–|to)\s*\d{1,2})?\s*\+?\s*years?(?:'s?|’s?)?"
        r"\s+(?:of\s+)?(?:[\w-]+\s+){0,4}?(?:work\s+)?experience"
    ),
    _rx(
        r"\b(\d{1,2})\s*(?:(?:-|–)\s*\d{1,2}\s*)?vuo(?:den|tta)\b(?:\s+[\wäö-]+){0,3}?\s+\w*kokemu"
    ),
)


def score(job: Job, config: RankConfig, today: date) -> Rank:
    points = 0.0
    reasons: list[str] = []

    def add(label: str, earned: float) -> None:
        nonlocal points
        points += earned
        if label:
            reasons.append(f"{label} {_signed(earned)}")

    if rule := _first(config.title, job.title):
        add(rule.label, rule.points)

    if job.location:
        for rule in config.location:
            if m := rule.match.search(job.location):
                add(rule.label or m.group(0).title(), rule.points)
                break
    elif config.unknown_location:
        add("no location", config.unknown_location)

    interest, keywords = _best_interest(job, config.interests)
    if keywords:
        add(", ".join(keywords), interest)

    start_text = f"{job.start or ''}\n{job.title}"
    if rule := _first(config.start, start_text):
        add(rule.label or "start", rule.points)

    if job.deadline:
        days = (job.deadline - today).days
        for deadline in sorted(config.deadline, key=lambda d: d.within_days):
            if 0 <= days <= deadline.within_days:
                add("closes today" if days == 0 else f"closes in {days} d", deadline.points)
                break

    years = years_of_experience(f"{job.title}\n{job.description}")
    if config.experience_points and years >= config.experience_years:
        add(f"asks {years}+ yrs", config.experience_points)

    return Rank(
        points,
        _stars(points, config),
        tuple(reasons),
        max_score(config),
        _places_by_relevance(job.location, config.location),
    )


def _places_by_relevance(location: str, rules: tuple[Rule, ...]) -> tuple[str, ...]:
    """Split "A; B; C" and order by the first location rule each place matches.

    Places no rule matches go last; ties keep the source's order.
    """
    places = [p.strip() for p in location.split(";") if p.strip()]

    def rank(place: str) -> int:
        return next((i for i, r in enumerate(rules) if r.match.search(place)), len(rules))

    return tuple(sorted(places, key=rank))


def max_score(config: RankConfig) -> float:
    """The best score any job could get: the top rule of every signal added up."""

    def top(values) -> float:
        return max(values, default=0)

    return (
        top(r.points for r in config.title)
        + top([config.unknown_location, *(r.points for r in config.location)])
        + top(r.points for r in config.interests)
        + top(r.points for r in config.start)
        + top(d.points for d in config.deadline)
    )


def rank_jobs(jobs: list[Job], config: RankConfig, today: date) -> list[RankedJob]:
    """Best first. Ties: the closer deadline first, then the newest posting."""
    ranked = [RankedJob(job, score(job, config, today)) for job in jobs]
    return sorted(ranked, key=_sort_key)


def _signed(points: float) -> str:
    """+3, +1.5: `g` drops a trailing .0."""
    return f"{points:+g}"


def _first(rules: tuple[Rule, ...], text: str) -> Rule | None:
    return next((rule for rule in rules if rule.match.search(text)), None)


def years_of_experience(text: str) -> int:
    """The most years of experience the text asks for (lower bound of a range); 0 if none."""
    return max((int(m.group(1)) for rx in _EXPERIENCE for m in rx.finditer(text)), default=0)


def _best_interest(job: Job, rules: tuple[Rule, ...]) -> tuple[float, list[str]]:
    """Points of the best tier (full in the title, half in the description) and its keywords."""
    best_points, best_keywords = 0.0, []
    for rule in rules:
        in_title = _keywords(rule.match, job.title)
        in_body = [] if rule.title_only else _keywords(rule.match, job.description)
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
