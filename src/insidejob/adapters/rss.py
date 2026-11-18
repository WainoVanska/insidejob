"""RSS 2.0 job feeds: Teamtailor career sites and WordPress job feeds.

`board` is the feed URL without the scheme, e.g. `careers.futurice.com/jobs.rss`
(Teamtailor: add `.rss` to the jobs page) or `gofore.com/en/careers/feed/`
(WordPress). It doubles as a readable state key: `rss:careers.futurice.com/jobs.rss`.

Standard fields: `title`, `link`, `guid` (id), `pubDate`, `description`. On top:

- Teamtailor adds `remoteStatus` (fully / hybrid / none) and, in the
  `https://teamtailor.com/locations` namespace, `tt:locations/tt:location/{tt:city,tt:country}`.
- WordPress puts the full text in `content:encoded` (`description` is only an excerpt).

WordPress feeds list only the newest posts (usually 10). That's fine for new-job
alerts, since new posts always appear at the top.
"""

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

from insidejob.models import Job, Workplace
from insidejob.text import html_to_text

TYPE = "rss"

NS = {
    "tt": "https://teamtailor.com/locations",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

# Teamtailor's remote options. "temporary" (remote for now) is left unknown on purpose.
REMOTE_STATUS = {
    "fully": Workplace.REMOTE,
    "hybrid": Workplace.HYBRID,
    "none": Workplace.ONSITE,
}


def feed_url(board: str) -> str:
    return board if board.startswith(("https://", "http://")) else f"https://{board}"


def fetch(client: httpx.Client, board: str, options: Mapping[str, str] | None = None) -> bytes:
    """Download the feed. Returns raw bytes so the XML parser honours its declared encoding."""
    response = client.get(feed_url(board))
    response.raise_for_status()
    return response.content


def parse(raw: bytes | str, board: str, company: str) -> list[Job]:
    """Turn an RSS 2.0 document into `Job`s. Pure: no I/O."""
    root = ET.fromstring(raw)
    source = f"{TYPE}:{board}"
    return [_parse_item(item, source, company) for item in root.iterfind("./channel/item")]


def _parse_item(item: ET.Element, source: str, company: str) -> Job:
    link = _text(item, "link")
    guid = _text(item, "guid") or link
    if not guid:
        raise ValueError(f"{source}: item without guid or link")

    body = _text(item, "content:encoded") or _text(item, "description")
    return Job(
        id=f"{source}:{guid}",
        source=source,
        company=company,
        title=_text(item, "title"),
        location=_locations(item),
        url=link or guid,
        posted_at=_parse_date(_text(item, "pubDate")),
        workplace=REMOTE_STATUS.get(_text(item, "remoteStatus").lower()),
        description=html_to_text(body),
    )


def _locations(item: ET.Element) -> str:
    places = []
    for loc in item.iterfind("tt:locations/tt:location", NS):
        parts = [_text(loc, "tt:city"), _text(loc, "tt:country")]
        place = ", ".join(p for p in parts if p) or _text(loc, "tt:name")
        if place and place not in places:
            places.append(place)
    return "; ".join(places)


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _text(element: ET.Element, path: str) -> str:
    return (element.findtext(path, default="", namespaces=NS) or "").strip()
