"""URL normalization: re-exports from shared ``crawliq_core`` package.

This module maintains backward compatibility for existing API imports.
The canonical implementation lives in ``packages/crawliq_core/url_normalize.py``.
"""

import sys
from pathlib import Path

_PACKAGES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "packages"
if str(_PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_DIR))

from crawliq_core.url_normalize import normalize_seed_url, normalize_url

__all__ = ["normalize_url", "normalize_seed_url"]
