"""Workday career site adapter.

Uses the JSON API that Workday's own career sites call (undocumented, but robots.txt
allows the career sites, and we only read public listings):

    POST https://<tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs
    {"appliedFacets": {...}, "limit": 20, "offset": 0, "searchText": ""}

`board` is the career site without the scheme, e.g.
`nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`.

Big employers list thousands of jobs worldwide (NVIDIA: 2,000+) and a page holds at most
20, so fetching everything hourly would be rude. The required `facet` option narrows it
server-side: the adapter reads the facets from the first page, finds the value whose
name equals `facet` (e.g. "Finland" under NVIDIA's "Locations" or KONE's "Location
Country"; the ids are opaque and differ per company) and pages through only those jobs.

Quirks handled here:
- `limit` above 20 is rejected (HTTP 400).
- An offset past the end doesn't return an empty page; it repeats results. So paging
  stops at the first page's `total`, and ids are de-duplicated.
- `locationsText` can be "3 Locations" or a bare city ("Hyvinkää"). Since the facet
  already guarantees the place, it's added: "Finland (3 locations)", "Hyvinkää, Finland".
- Listings have no description and only a relative date ("Posted 7 Days Ago"), so
  `description` stays empty and `posted_at` stays unknown.
"""

import re
import time
from collections.abc import Mapping
from typing import Any

import httpx

from insidejob.models import Job

TYPE = "workday"
OPTIONS = {"facet": True}  # option name -> required

PAGE_SIZE = 20
MAX_PAGES = 10  # hard stop: at most 200 jobs per board per run
PAGE_PAUSE = 0.5  # seconds between pages


def split_board(board: str) -> tuple[str, str, str]:
    """`nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite` -> (host, tenant, site)."""
    board = re.sub(r"^https?://", "", board).strip("/")
    host, _, site = board.partition("/")
    site = site.split("/")[-1]  # tolerate a locale prefix like en-US/
    if not host.endswith(".myworkdayjobs.com") or not site:
        raise ValueError(
            f"workday board must look like <tenant>.<wdN>.myworkdayjobs.com/<site>, got {board!r}"
        )
    return host, host.split(".")[0], site


def fetch(
    client: httpx.Client, board: str, options: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Page through the jobs under the configured facet. Returns {"facet", "jobPostings"}."""
    facet = (options or {}).get("facet", "")
    if not facet:
        raise ValueError("workday sources need options.facet, e.g. Finland")
    host, tenant, site = split_board(board)
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    # Facet ids are only discoverable from a response, so ask for 1 job to get them.
    first = _page(client, url, {}, offset=0, limit=1)
    param, value_id = find_facet(first.get("facets", []), facet)
    applied = {param: [value_id]}

    postings: dict[str, dict[str, Any]] = {}  # by externalPath: de-duplicates repeats
    total: int | None = None
    for number in range(MAX_PAGES):
        if number:
            time.sleep(PAGE_PAUSE)
        page = _page(client, url, applied, offset=number * PAGE_SIZE)
        if total is None:  # trust the first page's total; later pages may differ
            total = int(page.get("total") or 0)
        for posting in page.get("jobPostings", []):
            postings.setdefault(posting["externalPath"], posting)
        if (number + 1) * PAGE_SIZE >= total:
            break
    return {"facet": facet, "jobPostings": list(postings.values())}


def _page(
    client: httpx.Client,
    url: str,
    applied: dict[str, list[str]],
    *,
    offset: int,
    limit: int = PAGE_SIZE,
) -> dict[str, Any]:
    body = {"appliedFacets": applied, "limit": limit, "offset": offset, "searchText": ""}
    response = client.post(url, json=body, headers={"Accept": "application/json"})
    response.raise_for_status()
    return response.json()


def find_facet(facets: list[dict[str, Any]], name: str) -> tuple[str, str]:
    """Find (facetParameter, value id) for the facet value named `name`, at any depth."""
    found = _search(facets, name.strip().lower())
    if found is None:
        raise ValueError(f"no Workday facet value named {name!r}")
    return found


def _search(facets: list[dict[str, Any]], wanted: str) -> tuple[str, str] | None:
    for facet in facets:
        for value in facet.get("values", []):
            if "facetParameter" in value:  # a nested facet group, e.g. locationMainGroup
                found = _search([value], wanted)
                if found:
                    return found
            elif (value.get("descriptor") or "").strip().lower() == wanted:
                return facet["facetParameter"], value["id"]
    return None


def parse(raw: dict[str, Any], board: str, company: str) -> list[Job]:
    """Turn fetched postings into `Job`s. Pure: no I/O."""
    host, _, site = split_board(board)
    source = f"{TYPE}:{board}"
    facet = raw.get("facet", "")
    jobs = []
    for posting in raw.get("jobPostings", []):
        path = posting["externalPath"]
        jobs.append(
            Job(
                id=f"{source}:{_job_id(path)}",
                source=source,
                company=company,
                title=posting["title"].strip(),
                location=_location(posting.get("locationsText") or "", facet),
                url=f"https://{host}/{site}{path}",
            )
        )
    return jobs


def _job_id(path: str) -> str:
    """The requisition id at the end of the path.

    `/job/Espoo/Financial-Controller_R0666378-1` -> `R0666378-1`
    """
    tail = path.rstrip("/").rsplit("/", 1)[-1]
    return tail.rsplit("_", 1)[-1] if "_" in tail else path


def _location(text: str, facet: str) -> str:
    text = text.strip()
    if m := re.fullmatch(r"(\d+) Locations?", text, flags=re.IGNORECASE):
        return f"{facet} ({m.group(1)} locations)" if facet else text
    if facet and facet.lower() not in text.lower():
        return f"{text}, {facet}" if text else facet
    return text
