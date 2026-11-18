"""Where alerts go. Each notifier sends one digest of new jobs per run."""

from typing import Protocol

from insidejob.models import Job


class Notifier(Protocol):
    def send(self, jobs: list[Job]) -> None:
        """Deliver `jobs` (non-empty). Raise on failure so the run doesn't save state."""
        ...
