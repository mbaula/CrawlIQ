"""Unit tests for crawl frontier scheduling (no HTTP / DB)."""

from __future__ import annotations

from services.crawl_persistence import frontier_enqueues


def test_frontier_enqueues_child_depth_exceeds_max_depth() -> None:
    seen: set[str] = set()
    assert (
        frontier_enqueues(
            ["https://example.com/a"],
            current_depth=1,
            max_depth=1,
            max_pages=100,
            pages_crawled=0,
            seen=seen,
        )
        == []
    )


def test_frontier_enqueues_schedules_children_at_next_depth() -> None:
    seen: set[str] = {"https://example.com/seed"}
    got = frontier_enqueues(
        ["https://example.com/a", "https://example.com/b"],
        current_depth=0,
        max_depth=2,
        max_pages=100,
        pages_crawled=0,
        seen=seen,
    )
    assert set(got) == {
        ("https://example.com/a", 1),
        ("https://example.com/b", 1),
    }


def test_frontier_enqueues_skips_already_seen() -> None:
    seen: set[str] = {"https://example.com/a"}
    got = frontier_enqueues(
        ["https://example.com/a", "https://example.com/b"],
        current_depth=0,
        max_depth=2,
        max_pages=100,
        pages_crawled=0,
        seen=seen,
    )
    assert got == [("https://example.com/b", 1)]


def test_frontier_enqueues_respects_max_pages_budget() -> None:
    seen: set[str] = set()
    assert (
        frontier_enqueues(
            ["https://example.com/a", "https://example.com/b"],
            current_depth=0,
            max_depth=2,
            max_pages=2,
            pages_crawled=2,
            seen=seen,
        )
        == []
    )


def test_frontier_enqueues_schedules_all_targets_when_under_cap() -> None:
    """Enqueue uses current ``pages_crawled`` only to block at cap; BFS drain enforces ``max_pages``."""
    seen: set[str] = set()
    got = frontier_enqueues(
        ["https://example.com/a", "https://example.com/b", "https://example.com/c"],
        current_depth=0,
        max_depth=2,
        max_pages=2,
        pages_crawled=1,
        seen=seen,
    )
    assert len(got) == 3
