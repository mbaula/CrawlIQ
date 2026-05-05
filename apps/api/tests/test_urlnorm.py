"""URL canonicalization: ``normalize_url`` / ``normalize_seed_url``."""

import pytest

from services.urlnorm import normalize_seed_url, normalize_url


def test_normalize_seed_https_host_case_and_strip() -> None:
    assert normalize_seed_url("  HTTPS://Example.COM/path ") == "https://example.com/path"


def test_normalize_root_trailing_slash_equivalence() -> None:
    assert normalize_url("https://example.com") == "https://example.com/"
    assert normalize_url("https://example.com/") == "https://example.com/"


def test_normalize_strips_trailing_slash_on_non_root() -> None:
    assert normalize_url("https://example.com/foo/") == "https://example.com/foo"


def test_normalize_fragment_removed() -> None:
    assert normalize_url("https://example.com/page#section") == "https://example.com/page"


def test_normalize_utm_stripped_other_sorted() -> None:
    assert (
        normalize_url("https://example.com/page?utm_source=x&z=1&utm_medium=a&a=2")
        == "https://example.com/page?a=2&z=1"
    )


def test_normalize_only_utm_query_is_removed() -> None:
    assert normalize_url("https://example.com/?utm_campaign=z") == "https://example.com/"


def test_normalize_utm_key_case_insensitive() -> None:
    assert normalize_url("https://e.com/p?UTM_SOURCE=1&b=1") == "https://e.com/p?b=1"


def test_normalize_default_https_port_dropped() -> None:
    assert normalize_url("https://example.com:443/foo/") == "https://example.com/foo"


def test_normalize_default_http_port_dropped() -> None:
    assert normalize_url("http://example.com:80/bar/") == "http://example.com/bar"


def test_same_logical_urls_match() -> None:
    a = normalize_url("https://Example.COM:443/page/?utm_medium=x#h")
    b = normalize_url("https://example.com/page")
    assert a == b


def test_relative_resolved_against_base_with_trailing_slash() -> None:
    assert (
        normalize_url("next", base="https://example.com/topics/")
        == "https://example.com/topics/next"
    )


def test_relative_resolved_against_base_without_trailing_slash() -> None:
    assert normalize_url("next", base="https://example.com/topics") == "https://example.com/next"


def test_path_absolute_relative() -> None:
    assert normalize_url("/p", base="https://a.com/dir/here") == "https://a.com/p"


def test_scheme_relative_uses_base_scheme() -> None:
    assert (
        normalize_url("//cdn.example.org/x", base="https://main.example/a")
        == "https://cdn.example.org/x"
    )


def test_base_not_fully_canonical_utm_stripped_on_result() -> None:
    assert (
        normalize_url("x", base="https://a.com/dir/?utm_source=1")
        == "https://a.com/dir/x"
    )


def test_normalize_url_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_url("   ")


def test_normalize_relative_without_base_raises() -> None:
    with pytest.raises(ValueError, match="Base URL"):
        normalize_url("/alone")


def test_normalize_scheme_relative_without_base_raises() -> None:
    with pytest.raises(ValueError, match="Base URL"):
        normalize_url("//example.com/p")


def test_normalize_unsupported_scheme_raises() -> None:
    with pytest.raises(ValueError, match="http"):
        normalize_url("ftp://example.com/x")


def test_normalize_base_wrong_scheme_raises() -> None:
    with pytest.raises(ValueError, match="http"):
        normalize_url("x", base="ftp://a.com/")
