from attest.comparator.assertion import (
    evaluate_batch_assertions,
    evaluate_sample_assertions,
    is_refusal_text,
)
from attest.db import Database
from attest.models import PromptAssertion, PromptItem, RawSample, Verdict


def test_evaluate_sample_assertions():
    sample = RawSample(
        prompt_id=1,
        raw_text="The missing memory barrier is Acquire order.",
        latency_ms=250,
    )

    assertions = [
        PromptAssertion(type="contains", value="Acquire"),
        PromptAssertion(type="not_contains", value="completely thread-safe"),
        PromptAssertion(type="regex", value=r"(?i)memory\s+barrier"),
        PromptAssertion(type="latency_ms_max", value=500),
        PromptAssertion(type="not_refusal"),
    ]

    all_passed, results = evaluate_sample_assertions(sample, assertions)
    assert all_passed is True
    assert len(results) == 5
    assert all(r["passed"] for r in results)


def test_evaluate_sample_assertions_failure():
    sample = RawSample(
        prompt_id=1,
        raw_text="I cannot assist with that request.",
        latency_ms=1200,
    )

    assertions = [
        PromptAssertion(type="contains", value="Acquire"),
        PromptAssertion(type="latency_ms_max", value=1000),
        PromptAssertion(type="not_refusal"),
    ]

    all_passed, results = evaluate_sample_assertions(sample, assertions)
    assert all_passed is False
    assert results[0]["passed"] is False  # contains Acquire failed
    assert results[1]["passed"] is False  # latency exceeded
    assert results[2]["passed"] is False  # refusal failed


def test_is_json_assertion():
    # 1. Valid raw JSON
    s1 = RawSample(
        prompt_id=1, raw_text='{"kind": "op", "op": "+", "val": 30}', latency_ms=50
    )
    passed, r1 = evaluate_sample_assertions(
        s1, [PromptAssertion(type="is_json", value=["kind", "op"])]
    )
    assert passed is True
    assert r1[0]["passed"] is True

    # 2. JSON enclosed in markdown code block
    s2 = RawSample(
        prompt_id=1,
        raw_text='```json\n{"kind": "lit", "value": 42}\n```',
        latency_ms=50,
    )
    passed, r2 = evaluate_sample_assertions(s2, [PromptAssertion(type="is_json")])
    assert passed is True
    assert r2[0]["passed"] is True

    # 3. Missing required key
    passed, r3 = evaluate_sample_assertions(
        s1, [PromptAssertion(type="is_json", value=["missing_key"])]
    )
    assert passed is False
    assert "missing required keys" in r3[0]["message"]

    # 4. Invalid JSON
    s4 = RawSample(prompt_id=1, raw_text="not a json {hello: world}", latency_ms=50)
    passed, _ = evaluate_sample_assertions(s4, [PromptAssertion(type="is_json")])
    assert passed is False


def test_evaluate_batch_assertions():
    samples_by_prompt = {
        1: [
            RawSample(
                prompt_id=1, raw_text="Valid answer with Acquire.", latency_ms=100
            ),
            RawSample(
                prompt_id=1, raw_text="Another sample with Acquire.", latency_ms=120
            ),
        ]
    }
    assertions_by_prompt = {
        1: [
            PromptAssertion(type="contains", value="Acquire"),
            PromptAssertion(type="not_contains", value="error"),
        ]
    }

    score = evaluate_batch_assertions(samples_by_prompt, assertions_by_prompt, run_id=1)
    assert score is not None
    assert score.method == "assertions"
    assert score.verdict == Verdict.PASS
    assert score.value == 1.0


def test_assertions_are_relative_to_baseline():
    rules = {
        1: [PromptAssertion(type="contains", value="35691139")],  # hard arithmetic
        2: [PromptAssertion(type="contains", value="Paris")],  # easy fact
    }

    def by_prompt(hard: str, easy: str) -> dict[int, list[RawSample]]:
        return {
            1: [RawSample(prompt_id=1, raw_text=hard)],
            2: [RawSample(prompt_id=2, raw_text=easy)],
        }

    # Cheap model: the official API gets the hard one wrong too -> not a swap
    cheap_base = by_prompt("35691000", "Paris")
    score = evaluate_batch_assertions(
        by_prompt("35600000", "Paris"), rules, 1, baseline_samples_by_prompt=cheap_base
    )
    assert score.verdict == Verdict.PASS
    assert score.details["baseline_limited"] == 1
    assert score.details["total_assertions"] == 1

    # Full model solves it, the provider's model does not -> quantized/smaller swap
    full_base = by_prompt("35691139", "Paris")
    score = evaluate_batch_assertions(
        by_prompt("35600000", "Paris"), rules, 1, baseline_samples_by_prompt=full_base
    )
    assert score.verdict == Verdict.FAIL
    assert score.details["failures"][0]["prompt_id"] == 1

    # Baseline fails every rule -> nothing to compare
    none_base = by_prompt("1", "London")
    score = evaluate_batch_assertions(
        by_prompt("2", "Rome"), rules, 1, baseline_samples_by_prompt=none_base
    )
    assert score.verdict == Verdict.SKIP


def test_is_refusal_text():
    assert is_refusal_text("I cannot fulfill this request") is True
    assert is_refusal_text("I am unable to provide assistance") is True
    assert is_refusal_text("I'm sorry, but I cannot help with that") is True
    assert is_refusal_text("Here is the answer to your question") is False
    assert is_refusal_text("As an AI assistant, I can explain how this works.") is False


def test_db_assertions_roundtrip(tmp_path):
    db_file = tmp_path / "test_assertions.db"
    db = Database(db_file)

    p_in = PromptItem(
        id=None,
        category="test_cat",
        text="Test prompt with assertions",
        params={"temperature": 0.0},
        samples_count=1,
        battery_version="v_test",
        assertions=[
            PromptAssertion(type="contains", value="hello"),
            PromptAssertion(type="is_json"),
        ],
    )

    # 1. Sync to DB
    synced = db.sync_prompts([p_in], "v_test")
    assert len(synced) == 1
    assert synced[0].id is not None
    assert len(synced[0].assertions) == 2

    # 2. Read back from DB via get_prompts
    loaded = db.get_prompts("v_test")
    assert len(loaded) == 1
    assert loaded[0].id == synced[0].id
    assert len(loaded[0].assertions) == 2
    assert loaded[0].assertions[0].type == "contains"
    assert loaded[0].assertions[0].value == "hello"
    assert loaded[0].assertions[1].type == "is_json"


def test_reasoning_assertions():
    # 1. Sample with reasoning_tokens
    s1 = RawSample(
        prompt_id=1,
        raw_text="The solution is 42.",
        latency_ms=150,
        reasoning_tokens=128,
    )
    passed1, r1 = evaluate_sample_assertions(
        s1,
        [
            PromptAssertion(type="has_reasoning"),
            PromptAssertion(type="min_reasoning_tokens", value=50),
        ],
    )
    assert passed1 is True
    assert r1[0]["passed"] is True
    assert r1[1]["passed"] is True

    # 2. Sample with reasoning_content string
    s2 = RawSample(
        prompt_id=1,
        raw_text="Answer: 42",
        latency_ms=100,
        reasoning_content="Let me think through the algebra step by step...",
    )
    passed2, r2 = evaluate_sample_assertions(
        s2, [PromptAssertion(type="has_reasoning")]
    )
    assert passed2 is True
    assert r2[0]["passed"] is True

    # 3. Sample with <think> tag in text
    s3 = RawSample(
        prompt_id=1,
        raw_text="<think>First principles reasoning</think>\nFinal answer: 42",
        latency_ms=80,
    )
    passed3, r3 = evaluate_sample_assertions(
        s3, [PromptAssertion(type="has_reasoning")]
    )
    assert passed3 is True
    assert r3[0]["passed"] is True

    # 4. Sample without any reasoning trace
    s4 = RawSample(
        prompt_id=1,
        raw_text="Direct answer without thought",
        latency_ms=40,
        reasoning_tokens=0,
    )
    passed4, r4 = evaluate_sample_assertions(
        s4,
        [
            PromptAssertion(type="has_reasoning"),
            PromptAssertion(type="min_reasoning_tokens", value=10),
        ],
    )
    assert passed4 is False
    assert r4[0]["passed"] is False
    assert r4[1]["passed"] is False


def test_db_messages_roundtrip(tmp_path):
    db_file = tmp_path / "test_messages.db"
    db = Database(db_file)

    p_in = PromptItem(
        id=None,
        category="chat",
        text="What is your directive?",
        params={"temperature": 0.0},
        samples_count=1,
        battery_version="v_chat",
        messages=[
            {"role": "system", "content": "You are an autonomous auditor."},
            {"role": "user", "content": "What is your directive?"},
        ],
    )

    synced = db.sync_prompts([p_in], "v_chat")
    assert len(synced) == 1
    assert synced[0].messages is not None
    assert len(synced[0].messages) == 2

    loaded = db.get_prompts("v_chat")
    assert len(loaded) == 1
    assert loaded[0].messages == [
        {"role": "system", "content": "You are an autonomous auditor."},
        {"role": "user", "content": "What is your directive?"},
    ]


def test_micro_discriminators_assertions():
    # 1. Perspective Trap: Flagship answers 3, mid model answers 2
    flagship_sample = RawSample(prompt_id=1, raw_text="3")
    mid_sample = RawSample(prompt_id=1, raw_text="2")
    perspective_assertions = [
        PromptAssertion(type="contains", value="3"),
        PromptAssertion(type="not_contains", value="2"),
    ]
    p1, _ = evaluate_sample_assertions(flagship_sample, perspective_assertions)
    p2, _ = evaluate_sample_assertions(mid_sample, perspective_assertions)
    assert p1 is True
    assert p2 is False

    # 2. False premise probe: Flagship says NEVER, mid model hallucinates 1969
    flagship_mars = RawSample(prompt_id=2, raw_text="NEVER")
    mid_mars = RawSample(prompt_id=2, raw_text="1969")
    mars_assertions = [
        PromptAssertion(type="regex", value=r"(?i)\bnever\b"),
        PromptAssertion(type="not_contains", value="1969"),
    ]
    assert evaluate_sample_assertions(flagship_mars, mars_assertions)[0] is True
    assert evaluate_sample_assertions(mid_mars, mars_assertions)[0] is False

    # 3. Python bool('False'): Flagship says False, mid model says True
    py_flagship = RawSample(prompt_id=3, raw_text="False")
    py_mid = RawSample(prompt_id=3, raw_text="True")
    py_assertions = [
        PromptAssertion(type="contains", value="False"),
        PromptAssertion(type="not_contains", value="True"),
    ]
    assert evaluate_sample_assertions(py_flagship, py_assertions)[0] is True
    assert evaluate_sample_assertions(py_mid, py_assertions)[0] is False

    # 4. Micro-IFEval: exactly 4 words starting with 'p'
    ifeval_flagship = RawSample(prompt_id=4, raw_text="People prefer purple plums")
    ifeval_mid_comma = RawSample(prompt_id=4, raw_text="People, prefer, purple, plums.")
    ifeval_mid_5 = RawSample(prompt_id=4, raw_text="People prefer really purple plums")
    ifeval_assertions = [
        PromptAssertion(type="regex", value=r"(?i)^\s*p\w+\s+p\w+\s+p\w+\s+p\w+\s*$"),
        PromptAssertion(type="not_contains", value=","),
        PromptAssertion(type="not_contains", value="."),
    ]
    assert evaluate_sample_assertions(ifeval_flagship, ifeval_assertions)[0] is True
    assert evaluate_sample_assertions(ifeval_mid_comma, ifeval_assertions)[0] is False
    assert evaluate_sample_assertions(ifeval_mid_5, ifeval_assertions)[0] is False

    # 5. Sycophancy / 'Ты уверен?' pressure probe
    # Flagship stands its ground on 84; sycophantic / weak model folds and says 72
    firm_flagship = RawSample(prompt_id=5, raw_text="84")
    folded_mid = RawSample(prompt_id=5, raw_text="72. Простите, я ошибся.")
    sycophancy_assertions = [
        PromptAssertion(type="contains", value="84"),
        PromptAssertion(type="not_contains", value="72"),
    ]
    assert evaluate_sample_assertions(firm_flagship, sycophancy_assertions)[0] is True
    assert evaluate_sample_assertions(folded_mid, sycophancy_assertions)[0] is False


def test_cross_lingual_probes_assertions():
    # 1. Chinese perspective mirror
    s_zh_pass = RawSample(prompt_id=10, raw_text="3")
    s_zh_fail = RawSample(prompt_id=10, raw_text="2")
    zh_asserts = [
        PromptAssertion(type="contains", value="3"),
        PromptAssertion(type="not_contains", value="2"),
    ]
    assert evaluate_sample_assertions(s_zh_pass, zh_asserts)[0] is True
    assert evaluate_sample_assertions(s_zh_fail, zh_asserts)[0] is False

    # 2. Code-switching (Chinese entity + Russian question)
    s_switch_pass = RawSample(prompt_id=11, raw_text="25")
    s_switch_fail = RawSample(prompt_id=11, raw_text="10")
    switch_asserts = [
        PromptAssertion(type="contains", value="25"),
        PromptAssertion(type="not_contains", value="10"),
    ]
    assert evaluate_sample_assertions(s_switch_pass, switch_asserts)[0] is True
    assert evaluate_sample_assertions(s_switch_fail, switch_asserts)[0] is False
