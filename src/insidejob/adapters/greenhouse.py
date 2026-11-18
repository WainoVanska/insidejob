"""Greenhouse Job Board API adapter.

Docs: https://docs.greenhouse.io/job-board.html. GET endpoints are public and need
no auth. One request returns the whole board (no pagination). `content=true` adds
the description, departments and offices.
"""

import html
from datetime import date, datetime
from typing import Any

import httpx

from insidejob.models import Job
from insidejob.text import html_to_text

API_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
TYPE = "greenhouse"


def fetch(client: httpx.Client, board: str) -> dict[str, Any]:
    """Download a board's jobs, including descriptions."""
    response = client.get(API_URL.format(board=board), params={"content": "true"})
    response.raise_for_status()
    return response.json()


def parse(raw: dict[str, Any], board: str, company: str) -> list[Job]:
    """Turn a Job Board API response into `Job`s. Pure: no I/O.

    `company` comes from our config instead of the response's `company_name`, so
    boards like `supermetricsreferrals` still show the plain company name.
    """
    source = f"{TYPE}:{board}"
    return [_parse_job(item, source, company) for item in raw.get("jobs", [])]


def _parse_job(item: dict[str, Any], source: str, company: str) -> Job:
    location = (item.get("location") or {}).get("name") or ""
    return Job(
        id=f"{source}:{item['id']}",
        source=source,
        company=company,
        title=item["title"].strip(),
        location=location.strip(),
        url=item["absolute_url"],
        posted_at=_parse_datetime(item.get("first_published")),
        deadline=_parse_deadline(item.get("application_deadline")),
        # `content` is HTML that is itself HTML-escaped ("&lt;p&gt;…"), so unescape first.
        description=html_to_text(html.unescape(item.get("content") or "")),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    # `first_published` (not `updated_at`): edits must not make a job look new.
    return datetime.fromisoformat(value) if value else None


def _parse_deadline(value: str | None) -> date | None:
    # Real values look like "2026-11-24T16:45:00-05:00"; keep the date in that offset.
    return datetime.fromisoformat(value).date() if value else None
