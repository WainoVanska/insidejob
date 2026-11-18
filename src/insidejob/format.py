"""Human-readable job details, shared by the terminal output and the notifiers."""

from datetime import date

from insidejob.models import Job
from insidejob.rank import Rank

# One icon per detail, for the Discord alert.
ICONS = {"location": "📍", "workplace": "🏢", "employment": "💼", "start": "🗓️", "deadline": "⏳"}
# Match level (Rank.stars) as a traffic light.
MATCH_DOTS = {3: "🟢", 2: "🟡", 1: "🔴"}


MAX_PLACES = 3


def detail_parts(job: Job, *, icons: bool = False, places: tuple[str, ...] = ()) -> list[str]:
    """Location, workplace, employment, start, deadline: known values only.

    Values guessed by `enrich` are prefixed with `~`. With `icons`, each part starts
    with its emoji (📍 Helsinki, 🏢 hybrid, …). `places` (most relevant first, from the
    ranking) replaces the raw location and is cut to MAX_PLACES plus "+N more".
    """
    parts: list[str] = []

    def add(name: str, text: str) -> None:
        if name in job.inferred:
            text = f"~{text}"
        parts.append(f"{ICONS[name]} {text}" if icons else text)

    if places:
        shown = "; ".join(places[:MAX_PLACES])
        if len(places) > MAX_PLACES:
            shown += f" +{len(places) - MAX_PLACES} more"
        add("location", shown)
    elif job.location:
        add("location", job.location)
    if job.workplace:
        add("workplace", str(job.workplace))
    if job.employment:
        add("employment", str(job.employment))
    if job.start:
        add("start", f"{'starts' if icons else 'start'} {job.start}")
    if job.deadline:
        add("deadline", f"apply by {fi_date(job.deadline)}")
    return parts


def fi_date(day: date) -> str:
    """Finnish date format without zero padding: 15.1.2027."""
    return f"{day.day}.{day.month}.{day.year}"


def match_dot(rank: Rank) -> str:
    return MATCH_DOTS.get(rank.stars, MATCH_DOTS[1])


def score_text(rank: Rank) -> str:
    """`9.5 / 13`, or just `9.5` when the maximum isn't known."""
    return f"{rank.score:g} / {rank.out_of:g}" if rank.out_of else f"{rank.score:g}"


def reason_line(rank: Rank, prefix: str = "↳ ") -> str:
    """Why a job ranked where it did: `↳ intern +3 · Espoo +3 · C++, engine +1`."""
    return prefix + " · ".join(rank.reasons) if rank.reasons else ""


def plain(job: Job, rank: Rank | None = None) -> str:
    """Plain-text form for the terminal: match + title, details, and the reasons."""
    places = rank.places if rank else ()
    details = " · ".join([*detail_parts(job, places=places), job.url])
    text = f"{job.company} – {job.title}"
    if rank:
        text = f"{match_dot(rank)} {text} · {score_text(rank)}"
    text += f"\n    {details}"
    if rank and rank.reasons:
        text += f"\n    {reason_line(rank)}"
    return text
