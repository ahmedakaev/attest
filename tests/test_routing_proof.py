"""Unit tests for provider-reported routing metadata extraction, comparison, and Level 0 audit."""

from attest.comparator.quick import check_routing_proof
from attest.db import Database
from attest.detection.infrastructure import detect_infrastructure
from attest.detection.routing_proof import (
    RoutingProof,
    extract_routing_proof,
    verify_routing_proof_against_model,
)
from attest.models import RawSample, Verdict


def test_extract_openrouter_routing_proof():
    # Emulate the real payload intercepted from an OpenAI-compatible gateway for gpt-5.6-sol
    jwt_data = (
        "gAAAAABqtMxCTRxSVCgMYzaKJP1EzcO3s5ZLvnUWmkxLzmBD5tlBc_WWhFVWTZi5PEpiUZ6kt8LGncfONM8zDbRUmvG6cFRyp9GbpJRZTpiZEGX3_EjeGldRICxnGVrzVbJFU_meuJONJ4NQPNdU51dDCvgNMyQUDpSWb2w_9FbgANaNHEn6gqca315sDU1gpdTEF6T_mE4jkB1FGEm1FwvnR0vHNoxXmBmVqVosa6AeBoepNh-haLLrdRFtNLndt0710uisdSSBbVei-6IATkf0JwbXkjI8bm6SwSO1h5yX5jMjL3Y6Gh0qLTewL_1FEJoAsFQJf_HjN9zZ_A-ygMI9e00GFbewJoEhwOJO-JgSS7PtIAX44jE_mZkokh_Y8kFCBUy5DGk3dziCU0pCIzWtkYzy92vROsZK00lEd0-GfMpZ1km4dHqfntfH7vybVAiDQvd7nPnppfA96Zmt3ENqNMAgtOh9JmXYlLu9_ot6i4tL0VtKye3GpRCBLkdJh3V59JD4e8ifucucWxODiwgZ0Ds0pS6eQgdiLDi_2mRbPRHzTC1r1J6FdcStmxuoyf3QUeSr4o-eB89UEyuPoI9kbl_DmDrse1JuVFytmc0cPqAfuqx2xiH2ScL8dGMTSWd3R4anuxxtt_2XmNDbYAen990t1uZOoN3CiFYGBaN9QOLm8KkWAizb3436z8P2_0Mjoz3cWJscjngRf1epCiKLiwoUanKePjQrtPqq0Holk1AXAbzfu06B0oHmOWTSHfzptIGL9KNO4NvgkCDqv83tVvemXJKtJZa2CoxLkWckqCP-d87WLJAqPoBVNfOyZ_fDrxbFT6QLZWEiMLE9swEa2RdA5iM4VQTtyyCKkuF0g80gySrSAvhDDx1iy_q3aUwfxf37X-qhSXQKp23qqk1Lf9C1HUZSSL1LofPKOwpiS2hxuzW9ydzWJH2IZvLP72Vp-Zf_7LIbuHqL2U2hvhBeTM5MBsV-pxDUhcE80INQZx-L6Tmrk1TYB288xSJsH3ICwSK3hPmtVoQsJlqsC7Vp5pQvx3ela2fvSQ6eSQ8Vw2eOMJmsTpXQWpgkOdkGMi9CJDsx2UyFDk9bLKzJQSUKtWl9ld2mM3IzD4Cp6oZbpMQzpZLP-KZuS6yAHyJQGSRY_cZLJxAhDl3pcOQJxZQ6IlinoWzBGnKnef1Ke325sQYJrAQ-70ku4jetS6kGBP0bqa95bD3qEkE3dYAb8TSA0DDi1aUkdwlet3LYLm2MLFT6dLFaWamN6ZcOaycSlYOrxQq_cf-KH9W9ymrvmvJOQeyQqQwSF_sOATmOHUoMaZzHIugLFDVWykd2AcZrzGWIkFCLk8OKhRx5cmK5FovJdct7VZuQ-XpXHbWKuqc1f_9VvJTZrtOQG_h9hdb6OS-j3ADjnfArd2IaOsd1v4eiyGPKQ7vCVwBiQgwoHAExJTwFeg_3nKyrupptCkjWO1wtWDN6ueMWQ-wVsiJy1PE2nBODvIUyVtSeX6-3xt659OX-ei_PY72GFM9uykZRqV0icbO4fFneCsgGRM61AY2XuKCmjQnZTSgQlZU1EuJMKfRz0_DUZzmNwv4v-BwUWQepupav9Ki59J6Ag-B-82O8dxVUZIbxLQ=="
        ".eyJlbmRwb2ludF9zbHVnIjoib3BlbmFpL2dwdC01LjYtc29sLTIwMjYwNzA5fG9wZW5haSJ9"
    )
    raw_response = {
        "id": "gen-12345",
        "model": "gpt-5.6-sol",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Four",
                    "reasoning_details": [
                        {
                            "type": "reasoning.encrypted",
                            "data": jwt_data,
                            "format": "openai-responses-v1",
                        }
                    ],
                },
            }
        ],
    }

    proof = extract_routing_proof(raw_response)
    assert proof is not None
    assert proof.endpoint_slug == "openai/gpt-5.6-sol-20260709|openai"
    assert proof.upstream_model == "openai/gpt-5.6-sol-20260709"
    assert proof.upstream_provider == "openai"
    assert proof.model_snapshot == "20260709"
    assert proof.router == "openrouter"


def test_extract_openrouter_metadata_in_body():
    # Emulate OpenRouter response with openrouter_metadata field in body
    raw_response = {
        "id": "gen-67890",
        "model": "gpt-5.6-sol",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Test"}}],
        "openrouter_metadata": {
            "endpoint": "openai/gpt-5.6-sol-20260709|openai",
            "provider": "openai",
        },
    }
    proof = extract_routing_proof(raw_response)
    assert proof is not None
    assert proof.endpoint_slug == "openai/gpt-5.6-sol-20260709|openai"
    assert proof.upstream_model == "openai/gpt-5.6-sol-20260709"
    assert proof.upstream_provider == "openai"
    assert proof.model_snapshot == "20260709"


def test_extract_azure_served_model_header():
    # Emulate Azure OpenAI response header x-ms-served-model
    raw_response = {
        "id": "chatcmpl-azure",
        "model": "gpt-4o",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi"}}],
    }
    headers = {
        "x-ms-served-model": "gpt-4o-2024-08-06",
        "x-ms-region": "eastus2",
        "x-ms-request-id": "req-azure-123",
    }
    proof = extract_routing_proof(raw_response, headers=headers)
    assert proof is not None
    assert proof.endpoint_slug == "azure/gpt-4o-2024-08-06|azure"
    assert proof.upstream_model == "gpt-4o-2024-08-06"
    assert proof.upstream_provider == "azure"
    assert proof.model_snapshot == "2024-08-06"
    assert proof.router == "azure"

    # Test verification against claimed model
    is_match, reason = verify_routing_proof_against_model("gpt-4o", proof)
    assert is_match is True
    assert "Provider-reported routing matches" in reason
    assert "unsigned" in reason

    # Test mismatch when provider secretly returns gpt-4o-mini
    spoofed_azure_proof = extract_routing_proof(
        raw_response, headers={"x-ms-served-model": "gpt-4o-mini-2024-07-18"}
    )
    is_match_spoof, reason_spoof = verify_routing_proof_against_model(
        "gpt-4o", spoofed_azure_proof
    )
    assert is_match_spoof is False
    assert "Routing metadata mismatch" in reason_spoof


def test_verify_routing_proof_matching_and_mismatch():
    proof = RoutingProof(
        endpoint_slug="openai/gpt-5.6-sol-20260709|openai",
        upstream_model="openai/gpt-5.6-sol-20260709",
        upstream_provider="openai",
        model_snapshot="20260709",
    )

    # 1. Matching claim
    is_match, reason = verify_routing_proof_against_model("gpt-5.6-sol", proof)
    assert is_match is True
    assert "Provider-reported routing matches" in reason
    assert "unsigned" in reason

    # 2. Spoofed claim (client ordered gpt-5.6-sol, but router routed to gpt-4o-mini)
    spoofed_proof = RoutingProof(
        endpoint_slug="openai/gpt-4o-mini|openai",
        upstream_model="openai/gpt-4o-mini",
        upstream_provider="openai",
    )
    is_match, reason = verify_routing_proof_against_model("gpt-5.6-sol", spoofed_proof)
    assert is_match is False
    assert "Routing metadata mismatch" in reason


def test_check_routing_proof_score():
    proof_dict = {
        "endpoint_slug": "openai/gpt-5.6-sol-20260709|openai",
        "upstream_model": "openai/gpt-5.6-sol-20260709",
        "upstream_provider": "openai",
        "model_snapshot": "20260709",
        "router": "openrouter",
        "is_verified": True,
        "metadata": {},
    }

    samples_pass = [RawSample(prompt_id=1, raw_text="ok", routing_proof=proof_dict)]
    # Unsigned metadata can be forged, so a match is informational, never a PASS
    score_pass = check_routing_proof("gpt-5.6-sol", samples_pass)
    assert score_pass.verdict == Verdict.SKIP
    assert score_pass.value == 1.0
    assert score_pass.details["signature_verified"] is False

    score_fail = check_routing_proof("gpt-4o", samples_pass)
    assert score_fail.verdict == Verdict.FAIL
    assert score_fail.value == 0.0

    samples_none = [RawSample(prompt_id=1, raw_text="ok")]
    score_none = check_routing_proof("gpt-5.6-sol", samples_none)
    assert score_none.verdict == Verdict.SKIP


def test_detect_infrastructure_with_routing_proof():
    proof_dict = {
        "endpoint_slug": "openai/gpt-5.6-sol-20260709|openai",
        "upstream_model": "openai/gpt-5.6-sol-20260709",
        "upstream_provider": "openai",
        "router": "openrouter",
    }
    sample = RawSample(prompt_id=1, raw_text="hi", routing_proof=proof_dict)
    fp = detect_infrastructure(raw_samples=[sample])

    assert fp.proxy_gateway == "openrouter"
    assert fp.upstream_cloud == "openai"
    assert "маршрут по данным провайдера" in fp.summary("ru")
    assert "Verified routing proof" in fp.summary("en")
    assert fp.routing_proof == proof_dict


def test_database_routing_proof_persistence(tmp_path):
    db_file = tmp_path / "test_routing.db"
    db = Database(str(db_file))

    proof_dict = {
        "endpoint_slug": "openai/gpt-5.6-sol-20260709|openai",
        "upstream_model": "openai/gpt-5.6-sol-20260709",
        "upstream_provider": "openai",
    }
    sample = RawSample(
        prompt_id=1,
        raw_text="hello world",
        routing_proof=proof_dict,
        model_returned="gpt-5.6-sol",
    )

    # Test baseline persistence
    from attest.models import Target

    with db.connection() as conn:
        conn.execute(
            "INSERT INTO prompts (id, category, text, params, samples_count, battery_version) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "general", "ping", "{}", 1, "v1"),
        )
    db.save_target(Target(id="test-t", base_url="https://mock", model="gpt-5.6-sol"))
    bid = db.create_baseline_with_samples("test-t", "v1", [sample])

    loaded_baseline = db.get_baseline_samples(bid)
    assert len(loaded_baseline) == 1
    assert loaded_baseline[0].routing_proof is not None
    assert (
        loaded_baseline[0].routing_proof["endpoint_slug"]
        == "openai/gpt-5.6-sol-20260709|openai"
    )

    # Test run persistence
    rid = db.create_run("test-t", bid, "v1")
    db.save_run_samples(rid, [sample])

    loaded_run = db.get_run_samples(rid)
    assert len(loaded_run) == 1
    assert loaded_run[0].routing_proof is not None
    assert loaded_run[0].routing_proof["upstream_provider"] == "openai"
