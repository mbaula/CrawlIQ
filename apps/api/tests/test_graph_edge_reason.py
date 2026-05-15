"""Unit tests for ``format_graph_edge_reason``."""

from __future__ import annotations

import pytest

from services.graph_edge_reason import format_graph_edge_reason


def test_link_evidence() -> None:
    text = format_graph_edge_reason(
        "link",
        {"source": "direct_internal_link"},
        1.0,
    )
    assert text == "Direct link between these pages."


def test_url_hierarchy_with_paths() -> None:
    text = format_graph_edge_reason(
        "url_hierarchy",
        {"parent_path": "/", "child_path": "/docs"},
        0.9,
    )
    assert "Same URL hierarchy" in text
    assert "parent /" in text or "parent / →" in text
    assert "/docs" in text


def test_url_hierarchy_minimal() -> None:
    text = format_graph_edge_reason("url_hierarchy", None, 0.9)
    assert text.startswith("Same URL hierarchy")


def test_content_similarity_with_shared_terms() -> None:
    text = format_graph_edge_reason(
        "content_similarity",
        {"similarity": 0.42, "shared_terms": ["zebra", "apple", "mango"]},
        0.42,
    )
    assert "Similar page content" in text
    assert "0.420" in text
    assert "apple, mango, zebra" in text


def test_content_similarity_missing_shared_terms() -> None:
    text = format_graph_edge_reason(
        "content_similarity",
        {"similarity": 0.77},
        0.77,
    )
    assert "Similar page content" in text
    assert "0.770" in text
    assert "Shared terms" not in text


def test_near_duplicate_content_hash_match() -> None:
    text = format_graph_edge_reason(
        "near_duplicate",
        {"kind": "content_hash_match", "content_hash": "abc"},
        1.0,
    )
    assert "same extracted content hash" in text


def test_near_duplicate_high_similarity() -> None:
    text = format_graph_edge_reason(
        "near_duplicate",
        {"kind": "high_similarity", "similarity": 0.95},
        0.95,
    )
    assert "Very high content similarity" in text
    assert "0.950" in text


def test_unknown_edge_type() -> None:
    text = format_graph_edge_reason("not_a_real_edge", {"foo": 1}, 0.25)
    assert "Related by not_a_real_edge" in text
    assert "0.25" in text


@pytest.mark.parametrize(
    ("evidence", "weight"),
    [
        (None, 1.0),
        ("not-json", 1.0),
        ([1, 2, 3], 0.5),
        ({"unexpected": True}, 0.5),
    ],
)
def test_malformed_or_null_evidence_content_similarity(
    evidence: object,
    weight: float,
) -> None:
    text = format_graph_edge_reason("content_similarity", evidence, weight)
    assert text == "Similar page content."


def test_near_duplicate_malformed_evidence_uses_fallback() -> None:
    text = format_graph_edge_reason("near_duplicate", {"kind": "other"}, 0.8)
    assert "Related by near_duplicate" in text


def test_missing_weight_in_fallback() -> None:
    text = format_graph_edge_reason("manual", {}, None)
    assert "Related by manual" in text
    assert "unknown" in text


def test_shared_terms_edge_type_fallback() -> None:
    text = format_graph_edge_reason("shared_terms", {"shared_terms": ["a"]}, 1.0)
    assert "Related by shared_terms" in text


def test_semantic_similarity_with_terms() -> None:
    text = format_graph_edge_reason(
        "semantic_similarity",
        {"similarity": 0.5, "shared_terms": ["x", "y"]},
        0.5,
    )
    assert "Semantic similarity" in text
    assert "x" in text and "y" in text
