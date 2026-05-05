"""URL normalization: re-exports from shared ``crawliq_core`` package."""

from crawliq_core.url_normalize import normalize_seed_url, normalize_url

__all__ = ["normalize_url", "normalize_seed_url"]
