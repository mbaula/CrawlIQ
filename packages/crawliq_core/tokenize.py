"""Deterministic tokenizer for developer docs/search."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_DEFAULT_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "he",
        "her",
        "hers",
        "him",
        "his",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "not",
        "of",
        "on",
        "or",
        "our",
        "ours",
        "she",
        "so",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "too",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
        "yours",
    }
)

# Pre-normalization rules that preserve meaning for common dev tokens before we
# split on punctuation.
_DEV_TOKEN_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # languages/platforms
    (re.compile(r"(?<![0-9a-z])c\+\+(?![0-9a-z])", flags=re.IGNORECASE), "cpp"),
    (re.compile(r"(?<![0-9a-z])c#(?![0-9a-z])", flags=re.IGNORECASE), "csharp"),
    (re.compile(r"(?<![0-9a-z])f#(?![0-9a-z])", flags=re.IGNORECASE), "fsharp"),
    (re.compile(r"(?<![0-9a-z])asp\.net(?![0-9a-z])", flags=re.IGNORECASE), "aspnet"),
    (re.compile(r"(?<![0-9a-z])\.net(?![0-9a-z])", flags=re.IGNORECASE), "dotnet"),
    (re.compile(r"(?<![0-9a-z])node\.js(?![0-9a-z])", flags=re.IGNORECASE), "nodejs"),
    (re.compile(r"(?<![0-9a-z])next\.js(?![0-9a-z])", flags=re.IGNORECASE), "nextjs"),
    (re.compile(r"(?<![0-9a-z])vue\.js(?![0-9a-z])", flags=re.IGNORECASE), "vuejs"),
    # protocol / hashing shorthands commonly written with punctuation
    (re.compile(r"\bhttp\s*/\s*2\b", flags=re.IGNORECASE), "http2"),
    (re.compile(r"\bsha\s*-\s*256\b", flags=re.IGNORECASE), "sha256"),
)

_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")


def _apply_dev_token_rules(text: str) -> str:
    for pat, repl in _DEV_TOKEN_RULES:
        text = pat.sub(repl, text)
    return text


def tokenize(
    text: str,
    *,
    stopwords: Iterable[str] | None = None,
    min_len: int = 2,
    keep_numbers: bool = False,
) -> list[str]:
    """
    Convert text into searchable terms.

    - Deterministic: preserves left-to-right token order.
    - Drops pure numeric tokens by default (set ``keep_numbers=True`` to keep them).
    - Keeps mixed alphanumeric tokens (e.g. ``http2``, ``sha256``).
    """
    if not text:
        return []

    stop = set(_DEFAULT_STOPWORDS)
    if stopwords is not None:
        stop.update(unicodedata.normalize("NFKC", w).casefold() for w in stopwords)

    s = unicodedata.normalize("NFKC", text).casefold()
    s = _apply_dev_token_rules(s)
    s = _NON_ALNUM_RE.sub(" ", s)

    out: list[str] = []
    for raw in s.split():
        tok = raw.strip()
        if not tok:
            continue
        if len(tok) < min_len:
            continue
        if tok in stop:
            continue
        if tok.isdigit() and not keep_numbers:
            continue
        if not any("a" <= c <= "z" for c in tok):
            if not (keep_numbers and tok.isdigit()):
                continue
        out.append(tok)

    return out


def tokenize_many(
    texts: Iterable[str],
    *,
    stopwords: Iterable[str] | None = None,
    min_len: int = 2,
    keep_numbers: bool = False,
) -> list[str]:
    """Tokenize multiple inputs, concatenating results in order."""
    out: list[str] = []
    for t in texts:
        out.extend(tokenize(t, stopwords=stopwords, min_len=min_len, keep_numbers=keep_numbers))
    return out

