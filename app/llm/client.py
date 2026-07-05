"""Bring-your-own-key, multi-provider LLM client (Anthropic / OpenAI / Gemini).

The API key is supplied per request and used only to construct a transient client;
it is never written to disk, env, or logs. Provider is auto-detected from the key
format, or set explicitly. A mock mode (no key) runs the whole pipeline with
deterministic placeholder content for local dev and tests.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any


def _clean_text(s: str) -> str:
    """Drop chars that crash the provider HTTP layer (e.g. the "ascii codec cannot
    encode \\u2028" error from PDF text), keeping real content. Mirrors
    workflow.extract.clean_text; duplicated to avoid a circular import
    (workflow/__init__ -> engine -> llm.client).
    """
    if not s:
        return s
    s = s.replace("\u2028", "\n").replace("\u2029", "\n").replace("\ufeff", "")
    return "".join(c for c in s if c in "\n\t\r" or unicodedata.category(c)[0] != "C")


def _clean_key(k: str) -> str:
    """API keys go into an ASCII HTTP header (x-api-key / Authorization). A bad paste
    can embed a U+2028/U+2029 line separator, BOM, or stray whitespace, which crashes
    the request with "ascii codec can't encode \\u2028". Keep only printable ASCII."""
    return "".join(c for c in (k or "") if 33 <= ord(c) <= 126)


class LLMError(RuntimeError):
    pass


class _Truncated(LLMError):
    """Raised when model output looks cut off (unbalanced braces)."""


# BYOK Model Router — two tiers per provider. The SAME user key accesses both,
# so this lowers cost per résumé with no quality loss where it matters.
#   tier1 (light / lightweight): structural + mechanical work — résumé extraction,
#     JD dissection, gap analysis, quality-check repairs. Cheap and fast.
#   tier2 (heavy / heavyweight): narrative work a recruiter actually reads —
#     bullet rewriting, skills, summary. Highest quality.
#
# IDs are kept CURRENT on purpose. The older snapshot IDs sometimes specified for
# a two-tier setup — claude-3-haiku-20240307 (retired 2026-04-19),
# claude-3-5-sonnet-20240620 (retired 2025-10-28), llama3-8b-8192 / llama3-70b-8192
# (Groq-deprecated) — now 404 or error, so the same tier intent is mapped onto live
# models. tier2 is the user's chosen heavy model (overridable via `model`).
MODEL_CONFIG = {
    "anthropic":  {"tier1": "claude-haiku-4-5",      "tier2": "claude-sonnet-4-6"},
    "openai":     {"tier1": "gpt-4o-mini",           "tier2": "gpt-4o"},
    # Gemini 1.5 IDs are RETIRED (404 "not found for API version v1beta") — use 2.5.
    "gemini":     {"tier1": "gemini-2.5-flash",      "tier2": "gemini-2.5-pro"},
    "groq":       {"tier1": "llama-3.1-8b-instant",  "tier2": "llama-3.3-70b-versatile"},
    "perplexity": {"tier1": "sonar",                 "tier2": "sonar-pro"},
}

# Free-tier orchestration: when a model 404s (retired/unavailable) or the key's tier
# hits a quota wall (429), step DOWN this ladder and keep working — a free-tier key
# should produce a résumé with the best model it can actually run, not an error.
FALLBACK_LADDER = {
    "anthropic":  ["claude-sonnet-4-6", "claude-haiku-4-5"],
    "openai":     ["gpt-4o", "gpt-4o-mini"],
    "gemini":     ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
                   "gemini-2.0-flash"],
    "groq":       ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "perplexity": ["sonar-pro", "sonar"],
}

# Error shapes that mean "this MODEL won't serve you" (vs a transient blip):
_MODEL_UNAVAILABLE = re.compile(
    r"404|not.?found|does not exist|unsupported|deprecated|retired|"
    r"429|quota|rate.?limit|resource.?exhausted|insufficient", re.I)


def _next_model(provider: str, model: str) -> str | None:
    """The next (cheaper / more available) model after `model` in the provider ladder."""
    ladder = FALLBACK_LADDER.get(provider) or []
    if model in ladder and ladder.index(model) + 1 < len(ladder):
        return ladder[ladder.index(model) + 1]
    if model not in ladder and ladder:      # unknown/custom model -> start of ladder
        return ladder[0]
    return None

# Accepted spellings for the lightweight tier (the rest route to tier2).
_LIGHT_TIERS = {"light", "cheap", "tier1", "t1"}

PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT)",
    "gemini": "Google (Gemini)",
    "groq": "Groq (Llama)",
    "perplexity": "Perplexity (Sonar)",
}


def detect_provider(api_key: str) -> str | None:
    """Best-effort provider detection from key shape."""
    k = (api_key or "").strip()
    if k.startswith("gsk_"):
        return "groq"
    if k.startswith("pplx-"):
        return "perplexity"
    if not k:
        return None
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith(("AIza", "AQ.")):  # legacy + new-format Google AI Studio keys
        return "gemini"
    if k.startswith(("sk-", "sk-proj-")):
        return "openai"
    return None


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cheap_in: int = 0
    cheap_out: int = 0
    strong_in: int = 0
    strong_out: int = 0

    def add(self, i: int, o: int, tier: str = "strong") -> None:
        i, o = i or 0, o or 0
        self.input_tokens += i
        self.output_tokens += o
        if tier == "cheap":
            self.cheap_in += i
            self.cheap_out += o
        else:
            self.strong_in += i
            self.strong_out += o

    def as_dict(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cheap": {"in": self.cheap_in, "out": self.cheap_out},
                "strong": {"in": self.strong_in, "out": self.strong_out}}


def _extract_json(text: str) -> dict:
    """First complete JSON object, tolerant of ``` fences and prose; brace-counted."""
    t = (text or "").strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
        if m:
            t = m.group(1).strip()
    start = t.find("{")
    if start == -1:
        raise LLMError(f"No JSON object found in model output:\n{text[:400]}")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise _Truncated(f"Truncated JSON (output cut off):\n{text[-300:]}")


@dataclass
class LLMClient:
    mock: bool = False
    provider: str | None = None
    api_key: str = ""
    model: str = ""
    economy: bool = False  # Economy Mode: route EVERY step to tier1 (cheapest)
    usage: Usage = field(default_factory=Usage)
    _impl: Any = None
    _lock: Any = field(default_factory=threading.Lock)

    def __post_init__(self):
        if self.mock:
            return
        self.api_key = _clean_key(self.api_key)   # strip paste artifacts that break the header
        self.provider = self.provider or detect_provider(self.api_key)
        if self.provider not in MODEL_CONFIG:
            raise LLMError(
                "Could not determine the AI provider from your key. Use an Anthropic "
                "(sk-ant-…), OpenAI (sk-…), Google Gemini (AIza… or AQ…), Groq (gsk_…), "
                "or Perplexity (pplx-…) key."
            )
        self.model = self.model or MODEL_CONFIG[self.provider]["tier2"]
        self._impl = _make_impl(self.provider, self.api_key)

    def _tier_model(self, task_tier: str) -> str:
        """Resolve a model string for a task tier. Economy Mode forces tier1."""
        if self.economy or task_tier in _LIGHT_TIERS:
            return MODEL_CONFIG.get(self.provider, {}).get("tier1", self.model)
        return self.model  # heavy / tier2 = the user's chosen heavy model

    # -- public API: one structured step --
    def complete_json(self, cached_context: str, instruction: str, *,
                      mock: dict, max_tokens: int = 2000, max_retries: int = 3,
                      task_tier: str = "heavy") -> dict:
        if self.mock:
            return mock
        # Strip chars that crash the provider HTTP layer (PDF U+2028, BOMs, control
        # chars) — covers pasted JD text too, not just file uploads.
        cached_context = _clean_text(cached_context)
        instruction = _clean_text(instruction)
        model = self._tier_model(task_tier)
        # Usage is tracked per physical tier (so Economy Mode shows up as all-cheap).
        bucket = "cheap" if (self.economy or task_tier in _LIGHT_TIERS) else "strong"
        budget = max_tokens
        last_err: Exception | None = None
        # Extra attempts so a ladder walk (e.g. free-tier 429s) still gets real retries.
        for attempt in range(max_retries + len(FALLBACK_LADDER.get(self.provider) or [])):
            try:
                text, ti, to, truncated = self._impl(cached_context, instruction, budget, model)
                with self._lock:  # safe under parallel calls
                    self.usage.add(ti, to, bucket)
                if truncated:
                    # Bump happens once, in the _Truncated handler below — not here.
                    raise _Truncated(f"hit token cap at {budget}")
                return _extract_json(text)
            except _Truncated as e:
                last_err = e
                budget = min(budget * 2, 8000)
                time.sleep(min(2 ** attempt, 8))
            except Exception as e:  # noqa: BLE001
                last_err = e
                nxt = _next_model(self.provider, model) if _MODEL_UNAVAILABLE.search(str(e)) else None
                if nxt:                      # retired model / free-tier quota -> step down
                    model = nxt
                    continue                 # try the fallback immediately, no backoff
                time.sleep(min(2 ** attempt, 8))
        raise LLMError(f"LLM step failed after retries (last model tried: {model}): {last_err}")


# --------------------------- provider implementations ---------------------------
# Each returns (text, input_tokens, output_tokens, truncated).

def _make_impl(provider: str, api_key: str):
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        def call(ctx: str, instruction: str, budget: int, model: str):
            resp = client.messages.create(
                model=model, max_tokens=budget,
                system=[{"type": "text", "text": ctx,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": instruction}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            u = resp.usage
            return text, u.input_tokens, u.output_tokens, resp.stop_reason == "max_tokens"
        return call

    if provider in ("openai", "groq", "perplexity"):
        import openai
        # Groq + Perplexity are OpenAI-compatible — same SDK, different base URL.
        base = {"groq": "https://api.groq.com/openai/v1",
                "perplexity": "https://api.perplexity.ai"}.get(provider)
        client = openai.OpenAI(api_key=api_key, base_url=base)
        # Perplexity gates response_format by account tier — rely on the prompt +
        # tolerant brace-parser instead so every account works.
        kwargs = {} if provider == "perplexity" else {"response_format": {"type": "json_object"}}

        def call(ctx: str, instruction: str, budget: int, model: str):
            resp = client.chat.completions.create(
                model=model, max_tokens=budget, **kwargs,
                messages=[
                    {"role": "system", "content": ctx + "\n\nAlways respond with strict JSON only."},
                    {"role": "user", "content": instruction},
                ],
            )
            choice = resp.choices[0]
            text = choice.message.content or ""
            u = resp.usage
            return (text, u.prompt_tokens, u.completion_tokens,
                    choice.finish_reason == "length")
        return call

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        def call(ctx: str, instruction: str, budget: int, model: str):
            gm = genai.GenerativeModel(model, system_instruction=ctx)
            resp = gm.generate_content(
                instruction,
                generation_config={"response_mime_type": "application/json",
                                   "max_output_tokens": budget},
            )
            text = resp.text or ""
            um = getattr(resp, "usage_metadata", None)
            ti = getattr(um, "prompt_token_count", 0) if um else 0
            to = getattr(um, "candidates_token_count", 0) if um else 0
            truncated = False
            try:
                truncated = str(resp.candidates[0].finish_reason).endswith("MAX_TOKENS")
            except Exception:
                pass
            return text, ti, to, truncated
        return call

    raise LLMError(f"Unsupported provider: {provider}")


def get_client(api_key: str = "", provider: str = "", *, allow_mock: bool = True,
               economy: bool = False) -> LLMClient:
    """Build a client for this request's key. No key + allow_mock -> mock mode.

    economy=True  -> Economy Mode: every step runs on the cheapest (tier1) model.
    economy=False -> Precision Mode (default): light steps on tier1, narrative
                     steps (bullets/skills/summary) on tier2.
    """
    if os.environ.get("FORCE_MOCK") == "1":  # local dev / tests, never hits a real API
        return LLMClient(mock=True, economy=economy)
    if not api_key:
        if allow_mock:
            return LLMClient(mock=True, economy=economy)
        raise LLMError("An API key is required.")
    return LLMClient(provider=(provider or None), api_key=api_key, economy=economy)
