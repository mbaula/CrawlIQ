"""HTML parsing: re-exports from shared ``crawliq_core`` package."""

from crawliq_core.html_parse import parse_html
from crawliq_core.schemas import ParsedPage

__all__ = ["parse_html", "ParsedPage"]
