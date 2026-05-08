"""HTML parser and content extractor.

Extract title, readable text, and links from HTML. Uses BeautifulSoup + lxml.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, Tag

from crawliq_core.schemas import ParsedPage
from crawliq_core.url_normalize import normalize_url

if TYPE_CHECKING:
    from bs4 import NavigableString

_STRIP_TAGS = frozenset(
    {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside"}
)

_NAV_PATTERNS = re.compile(
    r"\b(nav|menu|footer|header|sidebar)\b", re.IGNORECASE
)

_SKIP_SCHEMES = frozenset({"mailto", "tel", "javascript", "data"})


def _should_remove_by_attrs(tag: Tag) -> bool:
    """Remove elements with navigation-related roles, aria-labels, or class/id names."""
    if getattr(tag, "attrs", None) is None:
        return False

    role = tag.get("role", "")
    if isinstance(role, str) and role.lower() == "navigation":
        return True

    aria = tag.get("aria-label", "")
    if isinstance(aria, str) and "navigation" in aria.lower():
        return True

    for attr in ("class", "id"):
        val = tag.get(attr)
        if val is None:
            continue
        text = " ".join(val) if isinstance(val, list) else str(val)
        if _NAV_PATTERNS.search(text):
            return True

    return False


def _extract_title(soup: BeautifulSoup) -> str:
    """og:title → <title> → first h1 → empty string."""
    og = soup.find("meta", property="og:title")
    if og and isinstance(og, Tag):
        content = og.get("content")
        if content and isinstance(content, str) and content.strip():
            return content.strip()

    title_tag = soup.find("title")
    if title_tag:
        text = title_tag.get_text(strip=True)
        if text:
            return text

    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if text:
            return text

    return ""


def _extract_text(soup: BeautifulSoup) -> str:
    """Visible text after removing non-content elements."""
    for tag in list(soup.find_all(_STRIP_TAGS)):
        tag.decompose()

    for tag in list(soup.find_all(True)):
        if not isinstance(tag, Tag):
            continue
        # Tag may have been decomposed earlier when its ancestor was removed.
        if getattr(tag, "attrs", None) is None or tag.parent is None:
            continue
        if _should_remove_by_attrs(tag):
            tag.decompose()

    raw = soup.get_text(separator=" ", strip=True)
    cleaned = re.sub(r"\s+", " ", raw).strip()
    return cleaned


def _looks_like_skip_scheme(href: str) -> bool:
    """Quick check for mailto:, tel:, javascript:, data: without full parse."""
    lower = href.lstrip().lower()
    for scheme in _SKIP_SCHEMES:
        if lower.startswith(scheme + ":"):
            return True
    return False


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Collect <a href>, resolve, normalize, dedupe while preserving order."""
    seen: set[str] = set()
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not isinstance(href, str):
            continue
        href = href.strip()
        if not href or href.startswith("#"):
            continue
        if _looks_like_skip_scheme(href):
            continue

        try:
            normalized = normalize_url(href, base=base_url)
        except ValueError:
            continue

        if normalized not in seen:
            seen.add(normalized)
            links.append(normalized)

    return links


def parse_html(html: str, base_url: str) -> ParsedPage:
    """
    Parse HTML and extract content.

    Parameters
    ----------
    html : str
        Raw HTML string (e.g. from ``fetch_html``).
    base_url : str
        The final URL after redirects—used to resolve relative links.

    Returns
    -------
    ParsedPage
        title, text, text_length, links.
    """
    soup = BeautifulSoup(html, "lxml")

    title = _extract_title(soup)

    soup_for_text = BeautifulSoup(html, "lxml")
    text = _extract_text(soup_for_text)

    links = _extract_links(soup, base_url)

    return ParsedPage(
        title=title,
        text=text,
        text_length=len(text),
        links=links,
    )
