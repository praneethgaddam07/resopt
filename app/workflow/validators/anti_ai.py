"""Anti-AI-tell filter: detect (and deterministically repair) banned words.

The ban-list mirrors the constraints in prompts.py so a post-generation scan
catches anything the prompt let slip. Repairs are conservative word swaps — the
goal is to never SHIP an AI-tell, while keeping the sentence readable.
"""
from __future__ import annotations

import re

# AI-tell words (mirrors prompts.py). Stems so "spearheading"/"leveraged" also match.
BANNED_AI_TELLS = [
    "delve", "spearhead", "synerg", "orchestrat", "tapestry", "unwavering",
    "foster", "harness", "testament", "paramount", "visionary", "cultivat",
    "leverage", "cutting-edge",
]
# Weak openers a bullet must never start with.
BANNED_WEAK_OPENERS = [
    "responsible for", "worked on", "helped with", "assisted",
    "duties included", "tasked with",
]

_AI_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in BANNED_AI_TELLS) + r")\w*\b", re.I)

# Deterministic last-resort swaps (used only if an LLM repair pass isn't available).
_SWAP = {
    "spearheaded": "led", "spearhead": "lead", "spearheading": "leading",
    "leveraging": "using", "leveraged": "used", "leverage": "use", "leverages": "uses",
    "synergy": "collaboration", "synergies": "collaboration", "synergized": "combined",
    "orchestrated": "coordinated", "orchestrating": "coordinating", "orchestrate": "coordinate",
    "harnessed": "used", "harnessing": "using", "harness": "use",
    "fostered": "built", "fostering": "building", "foster": "build",
    "delved": "examined", "delve": "examine", "cultivated": "built", "cultivating": "building",
    "cutting-edge": "advanced", "tapestry": "mix", "unwavering": "steady",
    "paramount": "critical", "visionary": "forward-looking", "testament": "proof",
}


def ai_tell_hits(text: str) -> list[str]:
    """Banned AI-tell words present in the text (lowercased, de-duped)."""
    return sorted({m.group(0).lower() for m in _AI_RE.finditer(text or "")})


def weak_opener(text: str) -> str | None:
    t = (text or "").lstrip().lower()
    return next((w for w in BANNED_WEAK_OPENERS if t.startswith(w)), None)


def scrub(text: str) -> str:
    """Deterministically replace banned words and strip a weak opener. Truthful and safe."""
    def repl(m: re.Match) -> str:
        return _SWAP.get(m.group(0).lower(), "")  # unmapped -> remove the word
    out = _AI_RE.sub(repl, text or "")
    wk = weak_opener(out)
    if wk:
        out = out[len(out.lower()) - len(out.lstrip().lower()):].lstrip()[len(wk):].lstrip()
        out = out[:1].upper() + out[1:] if out else out
    return re.sub(r"\s{2,}", " ", out).strip(" ,").strip()
