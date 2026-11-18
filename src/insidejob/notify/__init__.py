"""Where alerts go. Each notifier sends one digest per run: new jobs, or the top N."""

from typing import Protocol

from insidejob.rank import RankedJob


class Notifier(Protocol):
    def send(self, items: list[RankedJob], header: str | None = None) -> None:
        """Deliver `items` (non-empty, best first) under `header` (default: "N new jobs").

        Raise on failure so state isn't saved.
        """
        ...
