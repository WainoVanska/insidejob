"""Small builders shared by tests."""

from insidejob.models import Job


def make_job(job_id: str = "1", source: str = "greenhouse:acme", **overrides) -> Job:
    fields = {
        "id": f"{source}:{job_id}",
        "source": source,
        "company": "Acme",
        "title": "Summer Trainee",
        "location": "Helsinki, Finland",
        "url": f"https://example.com/{job_id}",
    }
    return Job(**(fields | overrides))


def greenhouse_board(*jobs: tuple[int, str, str]) -> dict:
    """A minimal Greenhouse API response: (id, title, location) per job."""
    return {
        "jobs": [
            {
                "id": job_id,
                "title": title,
                "location": {"name": location},
                "absolute_url": f"https://example.com/{job_id}",
                "first_published": "2026-11-01T09:00:00+02:00",
                "content": "&lt;p&gt;A 3-month traineeship. Hybrid work.&lt;/p&gt;",
            }
            for job_id, title, location in jobs
        ]
    }
