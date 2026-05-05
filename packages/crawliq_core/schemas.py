"""Shared Pydantic models for crawl pipeline data."""

from pydantic import BaseModel, Field


class ParsedPage(BaseModel):
    """Extracted content from an HTML page."""

    title: str = Field(description="Page title (og:title → <title> → first h1 → empty)")
    text: str = Field(description="Visible text after removing non-content tags")
    text_length: int = Field(description="Length of text in characters")
    links: list[str] = Field(description="Absolute normalized http(s) URLs from <a href>")
