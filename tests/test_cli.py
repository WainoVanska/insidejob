import pytest

from insidejob.cli import main


def test_run_dry_run_exits_zero():
    assert main(["run", "--dry-run"]) == 0


def test_missing_command_is_an_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
