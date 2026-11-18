"""Decide whether a job is relevant. Title and location only; other fields are display only."""

from insidejob.config import Filters
from insidejob.models import Job


def matches(job: Job, filters: Filters) -> bool:
    if not filters.title.search(job.title):
        return False
    if filters.exclude and filters.exclude.search(job.title):
        return False
    # An empty location passes: better an extra alert than a missed internship.
    if filters.location and job.location and not filters.location.search(job.location):
        return False
    return True
