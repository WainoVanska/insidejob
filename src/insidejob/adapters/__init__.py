"""Source adapters. Each module exposes `fetch()` (HTTP) and a pure `parse()`.

An adapter module may declare `OPTIONS = {"name": required}` for per-source settings
from the config's `options:`; config validation enforces it, and `fetch` receives them.
"""

from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from insidejob.adapters import ashby, greenhouse, rss, workday
from insidejob.models import Job


class Adapter(Protocol):
    TYPE: str

    def fetch(
        self, client: httpx.Client, board: str, options: Mapping[str, str] | None = None
    ) -> Any: ...

    def parse(self, raw: Any, board: str, company: str) -> list[Job]: ...


# Config `type:` value -> adapter module. Add new adapters here.
ADAPTERS: dict[str, Adapter] = {
    greenhouse.TYPE: greenhouse,
    rss.TYPE: rss,
    ashby.TYPE: ashby,
    workday.TYPE: workday,
}
