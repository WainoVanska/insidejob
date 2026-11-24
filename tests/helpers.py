"""Small builders shared by tests."""

from pathlib import Path

from insidejob.config import load_config
from insidejob.models import Job

# The example ranking from config.example.yaml (Helsinki area, graphics/AI interests,
# summer 2027; max 13 points). Tests that need location or interest rules use it, which
# also proves the example config parses and does what its comments say.
EXAMPLE_RANK = load_config(Path(__file__).parent.parent / "config.example.yaml").rank


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
