"""HTML parsing: re-exports from shared ``crawliq_core`` package.

The canonical implementation lives in ``packages/crawliq_core/html_parse.py``.
"""

import sys
from pathlib import Path

_PACKAGES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "packages"
if str(_PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_DIR))

from crawliq_core.html_parse import parse_html
from crawliq_core.schemas import ParsedPage

__all__ = ["parse_html", "ParsedPage"]
