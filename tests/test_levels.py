"""
Tests for battery includes and cumulative defence levels.
"""

from pathlib import Path

import httpx
import pytest
import respx

from attest.battery.loader import load_battery
from attest.config import AttestConfig
from attest.db import Database
from attest.models import Target
from attest.security import encrypt_api_key
from attest.service import AttestService, AttestServiceError

ROOT = Path(__file__).parent.parent / "batteries"


def _keys(prompts):
    return {(p.category, p.text) for p in prompts}


def test_each_level_contains_the_previous_one():
    previous: set = set()
    counts = []
    for n in (1, 2, 3, 4):
        version, prompts = load_battery(ROOT / f"level{n}.yaml")
        assert version == "levels-2026"
        assert all(p.battery_version == "levels-2026" for p in prompts)
        keys = _keys(prompts)
        assert previous <= keys, f"level{n} lost prompts of level{n - 1}"
        assert len(keys) == len(prompts), "duplicate prompts were not merged"
        previous = keys
        counts.append(sum(p.samples_count for p in prompts))
    assert counts == sorted(counts) and counts[0] == 44


def test_level1_is_iris_plus_tokenizer():
    _v, prompts = load_battery(ROOT / "level1.yaml")
    assert {p.category for p in prompts} == {"iris", "tokenizer_probe"}


def test_merge_keeps_largest_sample_count(tmp_path):
    (tmp_path / "a.yaml").write_text(
        'version: "a"\nprompts:\n  - category: c\n    text: "same"\n    samples: 3\n'
    )
    (tmp_path / "b.yaml").write_text(
        f'version: "b"\ninclude:\n  - {tmp_path / "a.yaml"}\n'
        "prompts:\n  - category: c\n    text: same\n    samples: 9\n"
        "  - category: c\n    text: other\n"
    )
    version, prompts = load_battery(tmp_path / "b.yaml")
    assert version == "b"
    by_text = {p.text: p for p in prompts}
    assert by_text["same"].samples_count == 9
    assert all(p.battery_version == "b" for p in prompts)


def test_include_errors(tmp_path):
    (tmp_path / "x.yaml").write_text(
        f'version: "x"\ninclude:\n  - {tmp_path / "y.yaml"}\n'
    )
    (tmp_path / "y.yaml").write_text(
        f'version: "y"\ninclude:\n  - {tmp_path / "x.yaml"}\n'
    )
    with pytest.raises(ValueError, match="cycle"):
        load_battery(tmp_path / "x.yaml")

    (tmp_path / "z.yaml").write_text(
        'version: "z"\ninclude:\n  - no_such_battery_anywhere\n'
    )
    with pytest.raises(ValueError, match="not found"):
        load_battery(tmp_path / "z.yaml")


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "m",
            "choices": [{"message": {"role": "assistant", "content": "4719"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        },
    )


@pytest.mark.asyncio
async def test_higher_level_run_on_lower_level_baseline_skips_uncovered(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "lv.db"
    db = Database(db_path)
    service = AttestService(db=db, config=AttestConfig(database=str(db_path)))
    target = Target(
        id="t",
        base_url="https://mock.api/v1",
        model="m",
        encrypted_key=encrypt_api_key("test-level-token"),
    )
    db.save_target(target)

    with respx.mock(base_url="https://mock.api/v1") as respx_mock:
        route = respx_mock.post("/chat/completions").mock(return_value=_ok_response())
        await service.capture_baseline_async(
            target=target, battery_path=str(ROOT / "level1.yaml")
        )
        assert route.call_count == 44

        route.reset()
        result = await service.audit_target_async(
            target=target, battery_path=str(ROOT / "level2.yaml")
        )
        # Only the level-1 prompts the baseline covers were paid for
        assert route.call_count == 44

    coverage = [s for s in result.scores if s.method == "baseline_coverage"]
    assert coverage and coverage[0].details["skipped_requests"] == 127 - 44


@pytest.mark.asyncio
async def test_baseline_from_unrelated_battery_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "lv2.db"
    db = Database(db_path)
    service = AttestService(db=db, config=AttestConfig(database=str(db_path)))
    target = Target(
        id="t",
        base_url="https://mock.api/v1",
        model="m",
        encrypted_key=encrypt_api_key("test-level-token"),
    )
    db.save_target(target)

    with respx.mock(
        base_url="https://mock.api/v1", assert_all_called=False
    ) as respx_mock:
        route = respx_mock.post("/chat/completions").mock(return_value=_ok_response())
        await service.capture_baseline_async(
            target=target, battery_path=str(ROOT / "iris.yaml")
        )
        route.reset()
        with pytest.raises(AttestServiceError, match="covers none"):
            await service.audit_target_async(
                target=target, battery_path=str(ROOT / "level1.yaml")
            )
        assert route.call_count == 0
