from datetime import date

import pytest

from insidejob.health import Health, HealthError, health_path

D1, D2, D3 = date(2026, 11, 18), date(2026, 11, 19), date(2026, 11, 20)


def test_failing_since_is_the_first_failure_and_clears_on_success():
    health = Health()
    health.record("gh:a", ok=True, today=D1)
    health.record("gh:a", ok=False, today=D2)
    health.record("gh:a", ok=False, today=D3)
    assert health.failing_since("gh:a") == D2
    assert health.boards["gh:a"]["last_ok"] == D1.isoformat()

    health.record("gh:a", ok=True, today=D3)
    assert health.failing_since("gh:a") is None


def test_round_trip_and_retain(tmp_path):
    path = health_path(tmp_path / "seen.json")
    assert path.name == "health.json"
    health = Health()
    health.record("gh:a", ok=False, today=D1)
    health.record("gh:old", ok=True, today=D1)
    health.retain(["gh:a"])
    health.save(path)
    loaded = Health.load(path)
    assert loaded.failing_since("gh:a") == D1
    assert "gh:old" not in loaded.boards


def test_missing_file_is_empty(tmp_path):
    assert Health.load(tmp_path / "health.json").boards == {}


def test_bad_file_raises(tmp_path):
    path = tmp_path / "health.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(HealthError):
        Health.load(path)
