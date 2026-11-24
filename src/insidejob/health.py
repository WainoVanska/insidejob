"""Per-board health, so the weekly heartbeat can say "failing since 18.11".

Stored next to `seen.json` as `health.json`:

    { "<source>:<board>": {"last_ok": "2026-11-24", "failing_since": "2026-11-20"} }

`failing_since` is only present while a board is failing. Dates, not timestamps, so the
file changes at most once a day per board and the hourly Action doesn't commit every run.
Kept apart from `seen.json` so the job state's format stays exactly as it was.
"""

import json
import os
from collections.abc import Iterable
from datetime import date
from pathlib import Path


class HealthError(Exception):
    pass


class Health:
    def __init__(self, boards: dict[str, dict[str, str]] | None = None) -> None:
        self.boards: dict[str, dict[str, str]] = boards or {}

    @classmethod
    def load(cls, path: Path) -> "Health":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise HealthError(f"cannot read health {path}: {exc}") from exc
        if not isinstance(data, dict) or not all(isinstance(v, dict) for v in data.values()):
            raise HealthError(f"{path}: expected {{source: {{last_ok, failing_since}}}}")
        return cls(data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        text = json.dumps(self.boards, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    def record(self, source: str, ok: bool, today: date) -> None:
        entry = self.boards.setdefault(source, {})
        if ok:
            entry["last_ok"] = today.isoformat()
            entry.pop("failing_since", None)
        else:
            entry.setdefault("failing_since", today.isoformat())

    def failing_since(self, source: str) -> date | None:
        value = self.boards.get(source, {}).get("failing_since")
        return date.fromisoformat(value) if value else None

    def retain(self, sources: Iterable[str]) -> None:
        keep = set(sources)
        for source in [s for s in self.boards if s not in keep]:
            del self.boards[source]


def health_path(state_path: Path) -> Path:
    """`health.json` lives next to the state file (on the `state` branch in the Action)."""
    return state_path.with_name("health.json")
