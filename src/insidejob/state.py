"""Which jobs we have already seen, persisted as `seen.json`.

    {
      "greenhouse:relex": {
        "8014266003": {"first_seen": "2026-11-18", "last_seen": "2026-11-18"}
      }
    }

Every fetched job is recorded, not only matching ones, so that loosening a filter later
doesn't alert on postings that have been up for weeks. Dates (not timestamps) keep the
file from changing on every hourly run, so the Action only commits when something
actually changed (at most once a day for `last_seen`).
"""

import json
import os
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from insidejob.models import Job

PRUNE_AFTER = timedelta(days=60)


class StateError(ValueError):
    """The state file exists but cannot be used."""


class State:
    def __init__(self, boards: dict[str, dict[str, dict[str, str]]] | None = None) -> None:
        self.boards = boards if boards is not None else {}

    @classmethod
    def load(cls, path: Path) -> "State":
        """Read state; a missing file means a fresh start."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"cannot read state {path}: {exc}") from exc
        if not isinstance(data, dict) or not all(isinstance(v, dict) for v in data.values()):
            raise StateError(f"{path}: expected {{source: {{job_id: {{...}}}}}}")
        return cls(data)

    def save(self, path: Path) -> None:
        """Write atomically, sorted, so diffs and commits stay small and stable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        text = json.dumps(self.boards, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    def knows(self, source: str) -> bool:
        return source in self.boards

    def update(self, source: str, jobs: Iterable[Job], today: date) -> set[str]:
        """Record `jobs` as seen today and return the ids of jobs that are new.

        The first time a source is seen, all its jobs are recorded silently: the result
        is empty, so adding a company never floods the channel with its backlog.
        """
        seeding = not self.knows(source)
        board = self.boards.setdefault(source, {})
        stamp = today.isoformat()
        new: set[str] = set()
        prefix = f"{source}:"
        for job in jobs:
            key = job.id.removeprefix(prefix)
            entry = board.get(key)
            if entry is None:
                board[key] = {"first_seen": stamp, "last_seen": stamp}
                if not seeding:
                    new.add(job.id)
            else:
                entry["last_seen"] = stamp
        return new

    def prune(self, sources: Iterable[str], today: date) -> int:
        """Forget jobs in `sources` that haven't been listed for `PRUNE_AFTER`.

        Only pass sources that were fetched successfully this run: a board that has been
        failing must keep its history, or it would look brand new when it recovers. Empty
        boards are kept, so a board with zero jobs isn't silently re-seeded later.
        """
        cutoff = (today - PRUNE_AFTER).isoformat()
        removed = 0
        for source in sources:
            board = self.boards.get(source, {})
            for key in [k for k, v in board.items() if v.get("last_seen", "") < cutoff]:
                del board[key]
                removed += 1
        return removed

    def retain(self, sources: Iterable[str]) -> None:
        """Drop boards that are no longer in the config."""
        keep = set(sources)
        for source in [s for s in self.boards if s not in keep]:
            del self.boards[source]
