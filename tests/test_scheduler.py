"""
Unit tests for recurring drift schedules and automated monitoring engine in Attest.
"""

from pathlib import Path

from attest.db import Database
from attest.models import Target


def test_scheduler_lifecycle(tmp_path: Path):
    db_file = tmp_path / "test_sched.db"
    db = Database(db_file)

    t = Target(id="test-t1", base_url="https://api.test/v1", model="gpt-5.6-luna")
    db.save_target(t)

    # 1. Create schedule
    s_id = db.create_or_update_schedule(
        target_id="test-t1",
        interval_hours=12,
        battery="quick",
        enabled=True,
    )
    assert s_id > 0

    schedules = db.list_schedules()
    assert len(schedules) == 1
    sched = schedules[0]
    assert sched.target_id == "test-t1"
    assert sched.interval_hours == 12
    assert sched.battery == "quick"
    assert sched.enabled is True

    # 2. Update existing schedule
    s_id2 = db.create_or_update_schedule(
        target_id="test-t1",
        interval_hours=24,
        battery="v1",
        enabled=True,
    )
    assert s_id2 == s_id
    updated_sched = db.get_schedule(s_id)
    assert updated_sched is not None
    assert updated_sched.interval_hours == 24
    assert updated_sched.battery == "v1"

    # 3. Test record_schedule_tick
    db.record_schedule_tick(s_id, interval_hours=24)
    ticked = db.get_schedule(s_id)
    assert ticked is not None
    assert ticked.last_run_at is not None
    assert ticked.next_run_at is not None

    # 4. Test delete schedule
    assert db.delete_schedule(s_id) is True
    assert db.get_schedule(s_id) is None
    assert len(db.list_schedules()) == 0
