from pathlib import Path

import httpx
import pytest
import respx

from attest.config import AttestConfig
from attest.db import Database
from attest.models import BaselineStatus, RunStatus, RunTrigger, Target, Verdict
from attest.security import encrypt_api_key
from attest.service import (
    AttestService,
    BaselineIntegrityError,
    BaselineNotFoundError,
)


@pytest.mark.asyncio
async def test_service_lifecycle_and_audit(tmp_path: Path):
    db_file = tmp_path / "test_svc.db"
    db = Database(db_file)
    cfg = AttestConfig(database=str(db_file))
    service = AttestService(db=db, config=cfg)

    target = Target(
        id="mock-target",
        base_url="https://mock.api/v1",
        model="gpt-4o",
        encrypted_key=encrypt_api_key("test-service-token"),
    )
    db.save_target(target)

    # Battery
    battery_file = tmp_path / "svc_battery.yaml"
    battery_file.write_text(
        """version: "test-v1"
prompts:
  - category: one_token
    text: "Pick a number 1-100"
    params: { max_tokens: 5, temperature: 1.0 }
    samples: 2
""",
        encoding="utf-8",
    )

    # 1. Estimation
    est = service.estimate_battery(str(battery_file))
    assert est["total_prompts"] == 1
    assert est["total_requests"] == 2

    # 2. Capture Baseline
    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-mock",
                    "model": "gpt-4o",
                    "choices": [{"message": {"role": "assistant", "content": "42"}}],
                    "usage": {"total_tokens": 10},
                },
            )
        )

        b_res = await service.capture_baseline_async(
            target=target,
            battery_path=str(battery_file),
            note="Service test baseline",
        )
        assert b_res.baseline_id is not None
        assert len(b_res.samples) == 2

        # 3. Audit Target
        audit_res = await service.audit_target_async(
            target=target,
            battery_path=str(battery_file),
            trigger=RunTrigger.MANUAL,
        )
        assert audit_res.run.status == RunStatus.COMPLETED
        assert audit_res.baseline.status == BaselineStatus.ACTIVE
        assert audit_res.overall_verdict in (Verdict.PASS, Verdict.WARN)
        assert audit_res.total_tokens == 20
        assert audit_res.est_cost_usd > 0
        assert len(audit_res.scores) > 0


def test_service_baseline_not_found(tmp_path: Path):
    db_file = tmp_path / "test_svc_nobaseline.db"
    db = Database(db_file)
    cfg = AttestConfig(database=str(db_file))
    service = AttestService(db=db, config=cfg)

    target = Target(
        id="no-b-target",
        base_url="https://mock.api/v1",
        model="gpt-4o",
    )
    db.save_target(target)

    with pytest.raises(BaselineNotFoundError):
        service.audit_target(target)


def test_service_baseline_integrity_tampering(tmp_path: Path):
    db_file = tmp_path / "test_svc_tamper.db"
    db = Database(db_file)
    cfg = AttestConfig(database=str(db_file))
    service = AttestService(db=db, config=cfg)

    target = Target(
        id="tamper-target",
        base_url="https://mock.api/v1",
        model="gpt-4o",
        encrypted_key=encrypt_api_key("test-tamper-token"),
    )
    db.save_target(target)

    battery_file = tmp_path / "svc_battery.yaml"
    battery_file.write_text(
        """version: "test-v1"
prompts:
  - category: one_token
    text: "Pick a digit"
    params: { max_tokens: 1 }
    samples: 1
""",
        encoding="utf-8",
    )

    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "cmpl-1",
                    "model": "gpt-4o",
                    "choices": [{"message": {"role": "assistant", "content": "1"}}],
                    "usage": {"total_tokens": 5},
                },
            )
        )
        b_res = service.capture_baseline(target=target, battery_path=str(battery_file))

    # Tamper with the raw_text in the database
    with db.connection() as conn:
        conn.execute(
            "UPDATE baseline_samples SET raw_text = 'tampered_malicious_content' WHERE baseline_id = ?",
            (b_res.baseline_id,),
        )

    # Verifying audit triggers BaselineIntegrityError
    with pytest.raises(BaselineIntegrityError):
        service.audit_target(target=target, battery_path=str(battery_file))


@pytest.mark.asyncio
async def test_sampling_error_names_the_key_used(tmp_path: Path):
    from attest.sampling.runner import SamplingBatteryError

    db = Database(tmp_path / "key.db")
    service = AttestService(
        db=db, config=AttestConfig(database=str(tmp_path / "key.db"))
    )
    battery = tmp_path / "b.yaml"
    battery.write_text(
        'version: "k"\nprompts:\n  - category: factual\n    text: "q"\n    samples: 2\n',
        encoding="utf-8",
    )
    stale = "test-or-key-433" + "0" * 58 + "fda"

    # The donor target holds a stale key; the new target has none and borrows it
    db.save_target(
        Target(
            id="donor",
            base_url="https://mock.api/v1",
            model="m",
            encrypted_key=encrypt_api_key(stale),
        )
    )
    borrower = Target(id="ref-new", base_url="https://mock.api/v1", model="m")
    db.save_target(borrower)

    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                401, json={"error": {"message": "User not found."}}
            )
        )
        with pytest.raises(SamplingBatteryError) as exc:
            await service.capture_baseline_async(
                target=borrower, battery_path=str(battery)
            )

    msg = str(exc.value)
    assert "User not found" in msg
    assert "test-or-key-...fda" in msg
    assert "borrowed from another target" in msg
    assert stale not in msg
