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
    assert out.body == "<html><body>ok</body></html>"
    assert out.elapsed_ms >= 0


def test_fetch_html_not_indexable_skipped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=b"{}",
        )

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/x", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "not_indexable"
    assert out.status_code == 200


def test_fetch_html_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"Content-Type": "text/plain"}, content=b"nope")

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/missing", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "http_error"
    assert out.status_code == 404
    assert out.retry_count == 0


def test_fetch_html_timeout(monkeypatch) -> None:
    monkeypatch.setattr("services.fetch_html.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/slow", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "timeout"
    assert out.retry_count == 3


def test_fetch_html_connect_error(monkeypatch) -> None:
    monkeypatch.setattr("services.fetch_html.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "connect"
    assert out.retry_count == 3


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
    assert out.retry_count == 0


def test_fetch_html_empty_url() -> None:
    out = fetch_html("   ", settings=Settings())
    assert isinstance(out, FetchHtmlFailure)
    assert out.kind == "invalid_url"
    assert out.retry_count == 0


def test_fetch_html_custom_user_agent() -> None:
    settings = Settings(crawl_http_user_agent="CustomBot/1.0")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "CustomBot/1.0"
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<p>a</p>")

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/", settings=settings, client=client)
    assert isinstance(out, FetchHtmlSuccess)


def test_fetch_html_retries_500_then_success(monkeypatch) -> None:
    monkeypatch.setattr("services.fetch_html.time.sleep", lambda _: None)
    n = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        if n == 1:
            return httpx.Response(500, headers={"Content-Type": "text/plain"}, content=b"err")
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>ok</html>")

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/x", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlSuccess)
    assert n == 2


def test_fetch_html_does_not_retry_404(monkeypatch) -> None:
    monkeypatch.setattr("services.fetch_html.time.sleep", lambda _: None)
    n = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return httpx.Response(404, headers={"Content-Type": "text/plain"}, content=b"nope")

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/x", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlFailure)
    assert out.status_code == 404
    assert out.retry_count == 0
    assert n == 1


def test_fetch_html_retries_429_then_success(monkeypatch) -> None:
    monkeypatch.setattr("services.fetch_html.time.sleep", lambda _: None)
    n = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        if n == 1:
            return httpx.Response(429, headers={"Content-Type": "text/plain"}, content=b"rate limit")
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>ok</html>")

    with _client(httpx.MockTransport(handler)) as client:
        out = fetch_html("https://example.com/x", settings=Settings(), client=client)
    assert isinstance(out, FetchHtmlSuccess)
    assert n == 2


def test_fetch_html_throttles_same_domain(monkeypatch) -> None:
    monkeypatch.setattr("services.fetch_html.time.sleep", lambda _: None)
    monkeypatch.setattr("services.fetch_html._last_fetch_at_by_domain", {})

    # Control monotonic time to force throttling on the second request.
    times = iter([100.0, 100.0, 100.2, 100.2])
    monkeypatch.setattr("services.fetch_html.time.monotonic", lambda: next(times))

    slept: list[float] = []

    def record_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("services.fetch_html.time.sleep", record_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html></html>")

    settings = Settings(crawl_domain_delay_seconds=1)
    with _client(httpx.MockTransport(handler)) as client:
        out1 = fetch_html("https://example.com/a", settings=settings, client=client)
        out2 = fetch_html("https://example.com/b", settings=settings, client=client)

    assert isinstance(out1, FetchHtmlSuccess)
    assert isinstance(out2, FetchHtmlSuccess)
    assert slept and slept[0] > 0


def test_fetch_html_does_not_throttle_different_domains(monkeypatch) -> None:
    monkeypatch.setattr("services.fetch_html._last_fetch_at_by_domain", {})
    monkeypatch.setattr("services.fetch_html.time.sleep", lambda _: (_ for _ in ()).throw(AssertionError("should not sleep")))
    monkeypatch.setattr("services.fetch_html.time.monotonic", lambda: 100.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html></html>")

    settings = Settings(crawl_domain_delay_seconds=1)
    with _client(httpx.MockTransport(handler)) as client:
        out1 = fetch_html("https://a.example.com/a", settings=settings, client=client)
        out2 = fetch_html("https://b.example.com/b", settings=settings, client=client)

    assert isinstance(out1, FetchHtmlSuccess)
    assert isinstance(out2, FetchHtmlSuccess)
