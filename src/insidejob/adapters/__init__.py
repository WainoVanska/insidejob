"""Source adapters. Each module exposes `fetch()` (HTTP) and a pure `parse()`."""

from typing import Any, Protocol

import httpx

from insidejob.adapters import ashby, greenhouse, rss
from insidejob.models import Job


class Adapter(Protocol):
    TYPE: str

    def fetch(self, client: httpx.Client, board: str) -> Any: ...

    def parse(self, raw: Any, board: str, company: str) -> list[Job]: ...


# Config `type:` value -> adapter module. Add new adapters here.
ADAPTERS: dict[str, Adapter] = {
    greenhouse.TYPE: greenhouse,
    rss.TYPE: rss,
    ashby.TYPE: ashby,
}
