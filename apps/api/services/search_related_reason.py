"""Human-readable relationship lines from ``page_graph_edges`` metadata."""

from __future__ import annotations

from typing import Any


def format_related_reason(*, edge_type: str, evidence: Any, weight: float) -> str:
    """
    Build a short explanation from stored ``edge_type`` and JSON ``evidence``.

    Unknown shapes fall back to ``{edge_type} (weight …)``.
    """
    et = (edge_type or "").strip() or "unknown"

    if et == "link":
        if isinstance(evidence, dict) and evidence.get("source") == "direct_internal_link":
            return "Direct link"
        return "Link"

    if et == "url_hierarchy":
        if isinstance(evidence, dict):
            pp = evidence.get("parent_path")
            cp = evidence.get("child_path")
            if pp is not None and cp is not None:
                return f"URL hierarchy (parent {pp} → child {cp})"
        return "URL hierarchy"

    if et == "content_similarity":
        parts: list[str] = ["Content similarity"]
        if isinstance(evidence, dict):
            sim = evidence.get("similarity")
            if sim is not None:
                try:
                    parts.append(f"score {float(sim):.3f}")
                except (TypeError, ValueError):
                    parts.append(f"score {sim}")
            st = evidence.get("shared_terms")
            if isinstance(st, list) and st:
                terms = ", ".join(str(t) for t in st[:12])
                if len(st) > 12:
                    terms += ", …"
                parts.append(f"shared terms: {terms}")
        return " · ".join(parts)

    if et == "near_duplicate":
        if isinstance(evidence, dict):
            kind = evidence.get("kind")
            if kind == "content_hash_match":
                return "Near duplicate (same content hash)"
            if kind == "high_similarity":
                sim = evidence.get("similarity")
                if sim is not None:
                    try:
                        return f"Near duplicate (high similarity {float(sim):.3f})"
                    except (TypeError, ValueError):
                        return f"Near duplicate (high similarity {sim})"
                return "Near duplicate (high similarity)"
        return "Near duplicate"

    if et == "shared_terms":
        if isinstance(evidence, dict):
            st = evidence.get("shared_terms") or evidence.get("terms")
            if isinstance(st, list) and st:
                return "Shared terms: " + ", ".join(str(t) for t in st[:15])
        return "Shared terms"

    w = float(weight) if weight is not None else 0.0
    return f"{et} (weight {w:.4g})"
