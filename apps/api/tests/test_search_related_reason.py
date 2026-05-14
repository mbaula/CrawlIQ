"""Unit tests for ``format_related_reason``."""

from __future__ import annotations

import pytest

from services.search_related_reason import format_related_reason


@pytest.mark.parametrize(
    ("edge_type", "evidence", "weight", "expected_substrings"),
    [
        ("link", {"source": "direct_internal_link"}, 1.0, ["Direct link"]),
        ("link", {}, 1.0, ["Link"]),
        (
            "url_hierarchy",
            {"parent_path": "/", "child_path": "/docs"},
            0.9,
            ["URL hierarchy", "/docs"],
        ),
        ("url_hierarchy", None, 0.9, ["URL hierarchy"]),
        (
            "content_similarity",
            {"similarity": 0.42, "shared_terms": ["a", "b"]},
            0.42,
            ["Content similarity", "0.420", "shared terms", "a", "b"],
        ),
        (
            "near_duplicate",
            {"kind": "content_hash_match"},
            1.0,
            ["content hash"],
        ),
        (
            "near_duplicate",
            {"kind": "high_similarity", "similarity": 0.95},
            0.95,
            ["high similarity", "0.950"],
        ),
        ("shared_terms", {"shared_terms": ["x", "y"]}, 1.0, ["Shared terms", "x", "y"]),
        ("custom_type", None, 0.25, ["custom_type", "weight", "0.25"]),
    ],
)
def test_format_related_reason_contains_expected_parts(
    edge_type: str,
    evidence: object,
    weight: float,
    expected_substrings: list[str],
) -> None:
    text = format_related_reason(edge_type=edge_type, evidence=evidence, weight=weight)
    for part in expected_substrings:
        assert part in text
