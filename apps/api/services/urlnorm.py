"""Canonical seed URL form for dedupe and policy (see docs/database-schema.md)."""

from urllib.parse import urlparse, urlunparse


def normalize_seed_url(seed: str) -> str:
    raw = seed.strip()
    if not raw:
        raise ValueError("seed URL is empty")

    parts = urlparse(raw)
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are supported")

    netloc = parts.netloc.strip().lower()
    if not netloc:
        raise ValueError("URL must include a host")

    path = parts.path if parts.path else "/"
    query = parts.query
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return normalized
