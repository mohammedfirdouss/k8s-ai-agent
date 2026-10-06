import pytest

from app.services import progress


def test_trackers_are_isolated_per_investigation():
    a = progress.create("inv-a", owner_id="user-a")
    b = progress.create("inv-b", owner_id="user-b")
    a.start_step("Checking Pods")

    assert progress.get("inv-a", "user-a").snapshot()["steps"][0]["status"] == "running"
    assert progress.get("inv-b", "user-b").snapshot()["steps"][0]["status"] == "pending"


def test_other_users_cannot_read_progress():
    progress.create("inv-private", owner_id="owner")
    assert progress.get("inv-private", "someone-else") is None


def test_duplicate_id_rejected():
    progress.create("inv-dup", owner_id="u")
    with pytest.raises(progress.InvestigationIdInUse):
        progress.create("inv-dup", owner_id="u")
