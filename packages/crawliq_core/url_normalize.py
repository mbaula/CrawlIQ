"""Canonical URL form for dedupe (seeds, pages, links).

Worker link extraction: resolve with the **page URL as fetched** (including its path and
trailing slash), then canonicalize the **result**:

    normalize_url(href, base=current_page_url)
"""

from __future__ import annotations

from yarl import URL

_UTM_KEYS_CF = frozenset(
    s.casefold()
    for s in (
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
    )
)


def _is_utm_key(key: str) -> bool:
    return key.casefold() in _UTM_KEYS_CF


def _strip_tracking_params(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(k, v) for k, v in pairs if not _is_utm_key(k)]


def _canonical_path(path: str) -> str:
    if not path or path == "/":
        return "/"
    stripped = path.rstrip("/")
    return stripped if stripped else "/"


def _filter_and_sort_query(u: URL) -> tuple[tuple[str, str], ...]:
    pairs = list(u.query.items())
    pairs = _strip_tracking_params(pairs)
    pairs.sort(key=lambda kv: (kv[0], kv[1]))
    return tuple(pairs)


def _needs_join_with_base(u: URL) -> bool:
    """Path-relative, or scheme-relative (``//host``) before a usable scheme exists."""
    if not u.is_absolute():
        return True
    return u.scheme == "" and bool(u.host)


def _finalize(url: URL) -> str:
    scheme = url.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are supported")
    if not url.host:
        raise ValueError("URL must include a host")

    path = _canonical_path(url.path)
    query_pairs = _filter_and_sort_query(url)

    out = URL.build(
        scheme=scheme,
        user=url.user or None,
        password=url.password or None,
        host=url.host,
        port=url.port,
        path=path,
        query=query_pairs if query_pairs else (),
        fragment="",
    )
    return str(out)


def normalize_url(url: str, base: str | None = None) -> str:
    """
    Return a canonical http(s) URL string.

    * Lowercases scheme and host (via ``yarl`` / IDNA).
    * Drops the fragment.
    * Drops default ports (``:80`` / ``:443``).
    * Removes trailing slash except on the root path (``.../`` stays for host root).
    * Removes ``utm_*`` query params (case-insensitive names); sorts remaining pairs.
    * If ``url`` is relative or scheme-relative, ``base`` must be an absolute http(s)
      URL; it is used **as given** for ``join`` (trimmed only), then the **result** is
      canonicalized—so base path semantics (e.g. trailing slash) match browser behavior.
    """
    raw = url.strip()
    if not raw:
        raise ValueError("URL is empty")

    u = URL(raw)
    if _needs_join_with_base(u):
        if base is None:
            raise ValueError("Base URL is required for relative URL resolution")
        b = base.strip()
        if not b:
            raise ValueError("Base URL is empty when provided")
        base_u = URL(b)
        if not base_u.scheme or base_u.scheme.lower() not in ("http", "https"):
            raise ValueError("Base URL must use http or https")
        if not base_u.host:
            raise ValueError("Base URL must include a host")
        u = base_u.join(u)

    return _finalize(u)


def normalize_seed_url(seed: str) -> str:
    """Normalize an absolute crawl seed (``http`` / ``https`` only)."""
    return normalize_url(seed)
