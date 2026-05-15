"""Deterministic human-readable explanations for ``page_graph_edges`` rows."""

from __future__ import annotations

from typing import Any, Mapping

_SIM_DISPLAY_DECIMALS = 3


def _evidence_as_dict(evidence: Any) -> dict[str, Any] | None:
    if isinstance(evidence, Mapping):
        return dict(evidence)
    return None


def _format_sim_display(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.{_SIM_DISPLAY_DECIMALS}f}"
    except (TypeError, ValueError):
        return str(value)


def _format_weight_strength(weight: float | None) -> str:
    if weight is None:
        return "unknown"
    try:
        return f"{float(weight):.4g}"
    except (TypeError, ValueError):
        return str(weight)


def _fallback(edge_type: str, weight: float | None) -> str:
    et = (edge_type or "").strip() or "unknown"
    return f"Related by {et} with strength {_format_weight_strength(weight)}."


def format_graph_edge_reason(edge_type: str, evidence: Any, weight: float | None) -> str:
    """
    Pure formatter: edge type, optional JSON evidence, and weight → one line (or short paragraph).

    Uses only stored metadata; no LLM. Unknown shapes fall back to ``Related by …``.
    """
    et = (edge_type or "").strip() or "unknown"
    ev = _evidence_as_dict(evidence)

    if et == "link":
        return "Direct link between these pages."

    if et == "url_hierarchy":
        base = (
            "Same URL hierarchy. One page appears to be a parent or child of the other."
        )
        if ev:
            pp = ev.get("parent_path")
            cp = ev.get("child_path")
            if pp is not None and cp is not None:
                return f"{base} Paths: parent {pp} → child {cp}."
            pu = ev.get("parent_url") or ev.get("parent_normalized")
            cu = ev.get("child_url") or ev.get("child_normalized")
            if pu is not None and cu is not None:
                return f"{base} URLs: {pu} → {cu}."
        return f"{base}"

    if et == "content_similarity":
        sim_s = None
        terms: list[str] = []
        if ev:
            sim_s = _format_sim_display(ev.get("similarity"))
            st = ev.get("shared_terms")
            if isinstance(st, list):
                terms = sorted({str(x) for x in st if x is not None and str(x).strip()})[:5]
        if terms:
            term_part = ", ".join(terms)
            if sim_s:
                return (
                    f"Similar page content (similarity {sim_s}). Shared terms: {term_part}."
                )
            return f"Similar page content. Shared terms: {term_part}."
        if sim_s:
            return f"Similar page content (similarity {sim_s})."
        return "Similar page content."

    if et == "near_duplicate":
        if ev and ev.get("kind") == "content_hash_match":
            return "Near duplicate. These pages have the same extracted content hash."
        if ev and ev.get("kind") == "high_similarity":
            sim_s = _format_sim_display(ev.get("similarity"))
            if sim_s:
                return f"Near duplicate. Very high content similarity (similarity {sim_s})."
            return "Near duplicate. Very high content similarity."
        return _fallback(et, weight)

    if et == "semantic_similarity":
        if ev:
            sim_s = _format_sim_display(ev.get("similarity") or ev.get("score"))
            st = ev.get("shared_terms") or ev.get("terms")
            if isinstance(st, list):
                labels = sorted({str(x) for x in st if x is not None and str(x).strip()})[:5]
                if labels:
                    joined = ", ".join(labels)
                    if sim_s:
                        return (
                            f"Semantic similarity (score {sim_s}). "
                            f"Overlapping signals: {joined}."
                        )
                    return f"Semantic similarity. Overlapping signals: {joined}."
            if sim_s:
                return f"Semantic similarity (score {sim_s})."
        return _fallback(et, weight)

    if et in ("shared_terms", "co_ranked", "manual"):
        return _fallback(et, weight)

    return _fallback(et, weight)
