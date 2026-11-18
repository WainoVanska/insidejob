import dataclasses

import pytest

from insidejob.models import Employment, Job, Workplace


def make_job(**overrides) -> Job:
    fields = {
        "id": "greenhouse:acme:1",
        "source": "greenhouse:acme",
        "company": "Acme",
        "title": "Summer Trainee",
        "location": "Helsinki, Finland",
        "url": "https://example.com/1",
    }
    return Job(**(fields | overrides))


def test_job_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        make_job().title = "changed"  # type: ignore[misc]


def test_description_ignored_in_equality():
    assert make_job(description="long text") == make_job(description="")


def test_description_hidden_from_repr():
    assert "long text" not in repr(make_job(description="long text"))


def test_enrich_style_update_marks_field_inferred():
    job = make_job()
    enriched = dataclasses.replace(
        job, workplace=Workplace.HYBRID, inferred=job.inferred | {"workplace"}
    )
    assert enriched.workplace == "hybrid"
    assert enriched.inferred == {"workplace"}
    assert job.workplace is None


def test_enum_values_are_display_strings():
    assert str(Employment.INTERNSHIP) == "internship"
    assert Employment("full-time") is Employment.FULL_TIME
