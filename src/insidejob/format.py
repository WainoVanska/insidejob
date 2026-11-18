"""Human-readable job details, shared by the terminal output and the notifiers."""

from datetime import date

from insidejob.models import Job
from insidejob.rank import Rank, stars_text


def detail_parts(job: Job) -> list[str]:
    """Location, workplace, employment, start, deadline: known values only.

    Values guessed by `enrich` are prefixed with `~`.
    """
    parts = [job.location] if job.location else []

    def add(name: str, text: str) -> None:
        parts.append(f"~{text}" if name in job.inferred else text)

    if job.workplace:
        add("workplace", str(job.workplace))
    if job.employment:
        add("employment", str(job.employment))
    if job.start:
        add("start", f"start {job.start}")
    if job.deadline:
        add("deadline", f"apply by {fi_date(job.deadline)}")
    return parts


def fi_date(day: date) -> str:
    """Finnish date format without zero padding: 15.1.2027."""
    return f"{day.day}.{day.month}.{day.year}"


def reason_line(rank: Rank) -> str:
    """Why a job ranked where it did: `↳ intern · Espoo · C++, engine`."""
    return "↳ " + " · ".join(rank.reasons) if rank.reasons else ""


def plain(job: Job, rank: Rank | None = None) -> str:
    """Plain-text form for the terminal: stars + title, details, and the reasons."""
    details = " · ".join([*detail_parts(job), job.url])
    head = f"{stars_text(rank.stars)} " if rank else ""
    text = f"{head}{job.company} – {job.title}\n    {details}"
    if rank and rank.reasons:
        text += f"\n    {reason_line(rank)}"
    return text
