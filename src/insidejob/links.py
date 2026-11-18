"""Turn a job link into a source: which hiring system, which board, and a company name.

Lets a user add a company by pasting the link of any of its job ads (or its job board)
instead of knowing `type` and `board`. Everything is read from the URL itself: no
network, no guessing.

    https://jobs.ashbyhq.com/iceye/1b8f…            → ashby, iceye
    https://job-boards.greenhouse.io/wolt/jobs/123  → greenhouse, wolt
    https://apply.workable.com/nitor/j/ABC123/      → workable, nitor
    https://hypehype.teamtailor.com/jobs/12-intern  → rss, hypehype.teamtailor.com/jobs.rss
    https://careers.futurice.com/jobs.rss           → rss, careers.futurice.com/jobs.rss
"""

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

SUPPORTED = (
    "Greenhouse (job-boards.greenhouse.io/<company>), "
    "Ashby (jobs.ashbyhq.com/<company>), "
    "Workable (apply.workable.com/<company>), "
    "Teamtailor (<company>.teamtailor.com) "
    "and job feeds (a link ending in .rss or /feed/)"
)


class LinkError(ValueError):
    """The link can't be turned into a source; the message says why in plain words."""


@dataclass(frozen=True)
class LinkSource:
    type: str
    board: str
    company: str  # a guess from the board name; `Name: link` in config overrides it


def parse_link(link: str) -> LinkSource:
    text = link.strip()
    if not text:
        raise LinkError("the link is empty")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    path = [p for p in parts.path.split("/") if p]
    if not host:
        raise LinkError(f"{link!r} doesn't look like a web link")

    if host.endswith("greenhouse.io"):
        return _greenhouse(host, path, parts.query, link)
    if host == "jobs.ashbyhq.com" and path:
        return _source("ashby", path[0])
    if host == "api.ashbyhq.com" and path[:2] == ["posting-api", "job-board"] and len(path) > 2:
        return _source("ashby", path[2])
    if host == "apply.workable.com":
        return _workable(path, link)
    if host.endswith(".teamtailor.com"):
        sub = host.removesuffix(".teamtailor.com")
        return LinkSource("rss", f"{host}/jobs.rss", _company_name(sub))
    if ".myworkdayjobs.com" in host:
        raise LinkError(
            "Workday sites need extra settings and are blocked on GitHub Actions; "
            "see the workday example in config.example.yaml (local runs only)"
        )
    if path and (path[-1].endswith(".rss") or path[-1] == "feed"):
        name = host.split(".")[-2] if "." in host else host
        return LinkSource("rss", host + parts.path, _company_name(name))
    if "gh_jid" in parse_qs(parts.query):
        raise LinkError(
            "this is a Greenhouse job shown on the company's own site, so the board name "
            "isn't in the link. Open the job's 'Apply' page or search the company on "
            "job-boards.greenhouse.io and paste that link instead"
        )
    raise LinkError(f"{host} isn't a supported job site. Supported: {SUPPORTED}")


def _greenhouse(host: str, path: list[str], query: str, link: str) -> LinkSource:
    params = parse_qs(query)
    if "for" in params:  # boards.greenhouse.io/embed/job_board?for=<board>
        return _source("greenhouse", params["for"][0])
    if host == "boards-api.greenhouse.io":  # /v1/boards/<board>/jobs
        if len(path) >= 3 and path[:2] == ["v1", "boards"]:
            return _source("greenhouse", path[2])
    elif path and path[0] != "embed":
        return _source("greenhouse", path[0])
    raise LinkError(f"can't find the company's board name in {link!r}")


def _workable(path: list[str], link: str) -> LinkSource:
    if path[:3] == ["api", "v3", "accounts"] and len(path) > 3:  # the API URL itself
        return _source("workable", path[3])
    if path and path[0] == "j":
        raise LinkError(
            "this short Workable link has no company name in it. Open the company's "
            "job list (apply.workable.com/<company>) and paste that link instead"
        )
    if path and path[0] != "api":
        return _source("workable", path[0])
    raise LinkError(f"can't find the company's name in {link!r}")


def _source(adapter: str, board: str) -> LinkSource:
    board = board.strip()
    if not board:
        raise LinkError("the link has no company board name in it")
    return LinkSource(adapter, board, _company_name(board))


def _company_name(slug: str) -> str:
    """'small-giant' → 'Small Giant'; short all-letter slugs like 'iceye' → 'Iceye'."""
    words = slug.replace("_", "-").split("-")
    return " ".join(w.capitalize() for w in words if w) or slug
