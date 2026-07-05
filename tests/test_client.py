"""JSON extraction robustness — regression for the truncation bug."""
import pytest

from app.llm.client import (_extract_json, _Truncated, LLMError, detect_provider,
                            MODEL_CONFIG, FALLBACK_LADDER, _next_model, LLMClient)


def test_model_fallback_ladder_on_retired_model_and_quota():
    """The exact field failure: gemini-1.5-* retired -> 404. The client must walk the
    ladder (pro -> flash -> …) instead of erroring, so free-tier keys still work."""
    c = LLMClient(provider="gemini", api_key="AQ.test-fake")
    calls = []

    def fake_impl(ctx, instruction, budget, model):
        calls.append(model)
        if model == "gemini-2.5-pro":
            raise RuntimeError("404 models/gemini-2.5-pro is not found for API version v1beta")
        if model == "gemini-2.5-flash":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded for this tier")
        return '{"ok": true}', 10, 5, False

    c._impl = fake_impl
    out = c.complete_json("ctx", "instr", mock=None, max_retries=2)
    assert out == {"ok": True}
    assert calls == ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]


def test_next_model_walks_and_ends():
    assert _next_model("gemini", "gemini-2.5-pro") == "gemini-2.5-flash"
    assert _next_model("anthropic", "claude-haiku-4-5") is None      # bottom of ladder
    assert _next_model("gemini", "custom-model") == "gemini-2.5-pro" # unknown -> ladder top
    for prov in MODEL_CONFIG:
        assert FALLBACK_LADDER.get(prov), f"{prov} missing a fallback ladder"


def test_detect_provider_all_key_shapes():
    assert detect_provider("sk-ant-abc") == "anthropic"
    assert detect_provider("sk-proj-abc") == "openai"
    assert detect_provider("AIzaXYZ") == "gemini"
    assert detect_provider("AQ.Ab8xxxxxxxxxxxxxxxx") == "gemini"  # new AI Studio format
    assert detect_provider("gsk_abc") == "groq"
    assert detect_provider("pplx-abc") == "perplexity"
    assert detect_provider("banana") is None
    # every detectable provider has a two-tier model config
    for prov in ("anthropic", "openai", "gemini", "groq", "perplexity"):
        assert {"tier1", "tier2"} <= MODEL_CONFIG[prov].keys()


def test_nested_object_in_code_fence():
    out = _extract_json('```json\n{"a": {"b": [1, 2]}, "c": "x}y"}\n```')
    assert out == {"a": {"b": [1, 2]}, "c": "x}y"}


def test_json_with_surrounding_prose():
    assert _extract_json('Sure: {"tier1": ["a", "b"]} done') == {"tier1": ["a", "b"]}


def test_truncated_output_raises_truncated():
    # Output cut off mid-array (the real proof-hierarchy failure) -> retryable.
    with pytest.raises(_Truncated):
        _extract_json('```json\n{"tier1": ["Designed a model across 100,000+ loan accounts')


def test_no_json_raises_plain_error_not_truncated():
    with pytest.raises(LLMError) as ei:
        _extract_json("the model refused and returned only prose")
    assert not isinstance(ei.value, _Truncated)
