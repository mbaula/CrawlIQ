"""HTML fetch: ``httpx.MockTransport`` for deterministic HTTP responses."""

import httpx

from config import Settings
from schemas.fetch_html import FetchHtmlFailure, FetchHtmlSuccess
from services.fetch_html import DEFAULT_HTTP_USER_AGENT, fetch_html


def _client(transport: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(
        transport=transport,
        follow_redirects=True,
        max_redirects=10,
        timeout=httpx.Timeout(30.0),
    )


def test_fetch_html_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "text/html" in request.headers.get("accept", "")
        assert request.headers.get("user-agent") == DEFAULT_HTTP_USER_AGENT
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=b"<html><body>ok</body></html>",
        )

    settings = Settings()
    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/path", settings=settings, client=client)
    assert isinstance(out, FetchHtmlSuccess)
    assert out.status_code == 200
    assert out.url == "https://example.com/path"
    assert out.final_url == "https://example.com/path"
    assert "text/html" in out.content_type
    assert out.html == "<html><body>ok</body></html>"
    assert out.elapsed_ms >= 0


def test_fetch_html_not_html_skipped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=b"{}",
        )

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/x", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "not_html"
    assert out.status_code == 200


def test_fetch_html_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"Content-Type": "text/plain"}, content=b"nope")

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/missing", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "http_error"
    assert out.status_code == 404


def test_fetch_html_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/slow", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "timeout"


def test_fetch_html_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "connect"


def test_fetch_html_redirect_then_success() -> None:
    n = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        if n == 1:
            return httpx.Response(
                302,
                headers={"Location": "https://example.com/final"},
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html></html>",
        )

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/start", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlSuccess)
    assert out.final_url.rstrip("/").endswith("final")
    assert n == 2


def test_fetch_html_oversized() -> None:
    body = b"x" * 200

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=body,
        )

    settings = Settings(crawl_max_response_bytes=100)
    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/big", settings=settings, client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "oversized"


def test_fetch_html_empty_url() -> None:
    out = fetch_html("   ", settings=Settings())
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "invalid_url"


def test_fetch_html_custom_user_agent() -> None:
    settings = Settings(crawl_http_user_agent="CustomBot/1.0")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "CustomBot/1.0"
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<p>a</p>")

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/", settings=settings, client=client)
    assert isinstance(out, FetchHtmlSuccess)
