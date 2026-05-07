"""Unit tests for search snippet generation."""

from services.search_pages import _build_snippet


def test_snippet_prefers_window_with_most_terms() -> None:
    body = (
        "Introduction paragraph without keywords. "
        "Middle section has fastapi mentioned once. "
        "Later section talks about both fastapi and async together which is ideal."
    )
    snippet = _build_snippet(
        title=None,
        body=body,
        highlight_terms=frozenset({"fastapi", "async"}),
    )
    assert "fastapi" in snippet.lower()
    assert "async" in snippet.lower()


def test_snippet_adds_ellipsis_prefix_when_not_at_start() -> None:
    body = "x" * 100 + " keyword appears here " + "y" * 100
    snippet = _build_snippet(
        title=None,
        body=body,
        highlight_terms=frozenset({"keyword"}),
    )
    assert snippet.startswith("…")


def test_snippet_no_prefix_ellipsis_when_at_start() -> None:
    body = "keyword appears at the very beginning of this text"
    snippet = _build_snippet(
        title=None,
        body=body,
        highlight_terms=frozenset({"keyword"}),
    )
    assert not snippet.startswith("…")
    assert "keyword" in snippet.lower()


def test_snippet_falls_back_to_title_when_body_empty() -> None:
    snippet = _build_snippet(
        title="FastAPI Documentation",
        body="",
        highlight_terms=frozenset({"fastapi"}),
    )
    assert "fastapi" in snippet.lower()


def test_snippet_returns_start_when_no_terms_found() -> None:
    body = "This text has no matching terms at all."
    snippet = _build_snippet(
        title=None,
        body=body,
        highlight_terms=frozenset({"nothere"}),
    )
    assert snippet.startswith("This text")
