from attest.models import (
    Baseline,
    BaselineStatus,
    Run,
    RunStatus,
    RunTrigger,
)


def test_enum_string_compatibility():
    # Enums are str subclasses
    assert BaselineStatus.ACTIVE == "active"
    assert BaselineStatus.SUPERSEDED == "superseded"
    assert BaselineStatus.INVALIDATED == "invalidated"

    assert RunStatus.RUNNING == "running"
    assert RunStatus.COMPLETED == "completed"
    assert RunStatus.FAILED == "failed"

    assert RunTrigger.MANUAL == "manual"
    assert RunTrigger.SCHEDULED == "scheduled"
    assert RunTrigger.WEB_UI == "web_ui"


def test_models_enum_defaults():
    b = Baseline(
        id=1,
        target_id="tgt-1",
        battery_version="v1",
        captured_at="2026-09-21T00:00:00Z",
    )
    assert b.status == BaselineStatus.ACTIVE
    assert b.status == "active"

    r = Run(
        id=1,
        target_id="tgt-1",
        baseline_id=1,
        battery_version="v1",
        started_at="2026-09-21T00:00:00Z",
    )
    assert r.status == RunStatus.RUNNING
    assert r.status == "running"
    assert r.trigger == RunTrigger.MANUAL
    assert r.trigger == "manual"
