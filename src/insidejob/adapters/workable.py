"""Workable adapter, via the public widget endpoint Workable's own job embeds use.

    GET https://apply.workable.com/api/v1/widget/accounts/<account>?details=true

`board` is the account slug from `apply.workable.com/<account>` (Varjo's is `varjo-1`).
One request per board, no pagination; `details=true` adds the HTML description.
`telecommuting: true` means remote; `false` doesn't say onsite vs hybrid, so it stays
unknown for `enrich` to look at.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from insidejob.models import Employment, Job, Workplace
from insidejob.text import html_to_text

API_URL = "https://apply.workable.com/api/v1/widget/accounts/{board}"
TYPE = "workable"

EMPLOYMENT = {
    "full-time": Employment.FULL_TIME,
    "part-time": Employment.PART_TIME,
    "internship": Employment.INTERNSHIP,
    "contract": Employment.FIXED_TERM,
    "temporary": Employment.FIXED_TERM,
}


def fetch(
    client: httpx.Client, board: str, options: Mapping[str, str] | None = None
) -> dict[str, Any]:
    response = client.get(API_URL.format(board=board), params={"details": "true"})
    response.raise_for_status()
    return response.json()


def parse(raw: dict[str, Any], board: str, company: str) -> list[Job]:
    """Turn a widget response into `Job`s. Pure: no I/O."""
    source = f"{TYPE}:{board}"
    return [_parse_job(item, source, company) for item in raw.get("jobs", [])]


def _parse_job(item: dict[str, Any], source: str, company: str) -> Job:
    return Job(
        id=f"{source}:{item['shortcode']}",
        source=source,
        company=company,
        title=item["title"].strip(),
        location=_locations(item),
        url=item.get("url") or item.get("shortlink") or "",
        posted_at=_parse_date(item.get("published_on") or item.get("created_at")),
        workplace=Workplace.REMOTE if item.get("telecommuting") else None,
        employment=EMPLOYMENT.get((item.get("employment_type") or "").strip().lower()),
        description=html_to_text(item.get("description") or ""),
    )


def _locations(item: dict[str, Any]) -> str:
    places = []
    entries = item.get("locations") or [{"city": item.get("city"), "country": item.get("country")}]
    for loc in entries:
        place = ", ".join(
            p.strip() for p in (loc.get("city"), loc.get("country")) if p and p.strip()
        )
        if place and place not in places:
            places.append(place)
    return "; ".join(places)


def _parse_date(value: str | None) -> datetime | None:
    """Workable gives a date ("2026-09-23"); keep it as midnight UTC."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None
