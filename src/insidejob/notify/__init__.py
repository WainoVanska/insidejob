"""Where alerts go. Each notifier sends one digest of new jobs per run."""

from typing import Protocol

from insidejob.rank import RankedJob


class Notifier(Protocol):
    def send(self, items: list[RankedJob]) -> None:
        """Deliver `items` (non-empty, best first). Raise on failure so state isn't saved."""
        ...
