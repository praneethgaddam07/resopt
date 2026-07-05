"""Metric-preservation validator.

Truth rule: every number that appears in a GENERATED bullet must already exist in
the candidate's SOURCE (master-résumé) bullets. A number in the output that isn't
in the source is a rounded / inflated / invented metric — a violation. This is the
deterministic backstop behind the prompt's "preserve every metric exactly" rule.
"""
from __future__ import annotations

import re

# Numbers with optional $/% and common units (18, 18%, $1.2M, 10,000+, 0.94, 3-6).
_METRIC_RE = re.compile(r"\$?\d[\d,]*\.?\d*\s?(?:%|percent|k|m|bn|x|hrs?|hours?|days?|weeks?|months?|years?|bps)?", re.I)


def _norm(token: str) -> str:
    """Reduce a metric token to its bare numeric value for comparison (18% -> '18')."""
    return re.sub(r"[^\d.]", "", token).strip(".") or ""


def extract_numbers(text: str) -> set[str]:
    return {_norm(m.group(0)) for m in _METRIC_RE.finditer(text or "") if _norm(m.group(0))}


def source_numbers(*bullet_groups: list[str]) -> set[str]:
    """Union of every number in the candidate's original bullets (the allowed set)."""
    allowed: set[str] = set()
    for group in bullet_groups:
        for b in group:
            allowed |= extract_numbers(b)
    return allowed


def bad_numbers(bullet: str, allowed: set[str]) -> list[str]:
    """Numbers in this generated bullet that are NOT in the source set."""
    return sorted(n for n in extract_numbers(bullet) if n not in allowed)


def strip_unbacked(bullet: str, allowed: set[str]) -> str:
    """Last-resort deterministic fix: remove metric tokens not backed by the source,
    so a hallucinated number can never ship (truthful over pretty)."""
    def repl(m: re.Match) -> str:
        return m.group(0) if _norm(m.group(0)) in allowed or not _norm(m.group(0)) else ""
    out = re.sub(r"\s{2,}", " ", _METRIC_RE.sub(repl, bullet)).strip()
    out = re.sub(r"\s+([,.])", r"\1", out).strip(" ,")
    return (out + ".") if out and not out.endswith(".") else out
