"""Ashby public job posting API adapter.

Docs: https://developers.ashbyhq.com/docs/public-job-posting-api. No auth, one request
per board, no pagination. Unlike Greenhouse, Ashby *lists* workplace and employment
type, so those come through as listed values (not inferred).
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import httpx

from insidejob.models import Employment, Job, Workplace

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"
TYPE = "ashby"

WORKPLACE = {
    "OnSite": Workplace.ONSITE,
    "Hybrid": Workplace.HYBRID,
    "Remote": Workplace.REMOTE,
}

# Ashby describes hours/contract, not the role: ICEYE's "Intern Lab" jobs are FullTime.
EMPLOYMENT = {
    "FullTime": Employment.FULL_TIME,
    "PartTime": Employment.PART_TIME,
    "Intern": Employment.INTERNSHIP,
    "Contract": Employment.FIXED_TERM,
    "Temporary": Employment.FIXED_TERM,
}


def fetch(
    client: httpx.Client, board: str, options: Mapping[str, str] | None = None
) -> dict[str, Any]:
    response = client.get(API_URL.format(board=board), params={"includeCompensation": "false"})
    response.raise_for_status()
    return response.json()


def parse(raw: dict[str, Any], board: str, company: str) -> list[Job]:
    """Turn a job board response into `Job`s, skipping unlisted postings. Pure: no I/O."""
    source = f"{TYPE}:{board}"
    return [
        _parse_job(item, source, company)
        for item in raw.get("jobs", [])
        if item.get("isListed", True) is not False
    ]


def _parse_job(item: dict[str, Any], source: str, company: str) -> Job:
    return Job(
        id=f"{source}:{item['id']}",
        source=source,
        company=company,
        title=item["title"].strip(),
        location=_locations(item),
        url=item["jobUrl"],
        posted_at=datetime.fromisoformat(item["publishedAt"]) if item.get("publishedAt") else None,
        workplace=WORKPLACE.get(item.get("workplaceType") or ""),
        employment=EMPLOYMENT.get(item.get("employmentType") or ""),
        description=(item.get("descriptionPlain") or "").strip(),
    )


def _locations(item: dict[str, Any]) -> str:
    """Primary + secondary locations as "City, Country; City, Country"."""
    places = [_place(item.get("location"), item.get("address"))]
    for secondary in item.get("secondaryLocations") or []:
        if isinstance(secondary, dict):
            places.append(_place(secondary.get("location"), secondary.get("address")))
        elif isinstance(secondary, str):
            places.append(secondary.strip())
    unique = []
    for place in places:
        if place and place not in unique:
            unique.append(place)
    return "; ".join(unique)


def _place(name: str | None, address: dict[str, Any] | None) -> str:
    """Add the address country when the name lacks it: Espoo -> "Espoo, Finland".

    This helps the location filter, which looks for e.g. "finland".
    """
    name = (name or "").strip()
    postal = (address or {}).get("postalAddress") or {}
    country = (postal.get("addressCountry") or "").strip()
    if name and country and country.lower() not in name.lower():
        return f"{name}, {country}"
    return name or country
