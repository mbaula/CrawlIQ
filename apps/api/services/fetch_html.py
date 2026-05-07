"""HTTP HTML fetch: sync ``httpx``, retries, timeouts, strict ``text/html``."""

from __future__ import annotations

import threading
import time

import httpx
from yarl import URL

from config import Settings, get_settings
from schemas.fetch_html import FetchHtmlFailure, FetchHtmlSuccess

DEFAULT_HTTP_USER_AGENT = "CrawlIQ/0.1"

_domain_lock = threading.Lock()
_last_fetch_at_by_domain: dict[str, float] = {}


def _effective_user_agent(settings: Settings) -> str:
    ua = (settings.crawl_http_user_agent or "").strip()
    return ua if ua else DEFAULT_HTTP_USER_AGENT


def _mime_without_params(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";")[0].strip().lower() or None


def _is_html_content_type(content_type: str | None) -> bool:
    return _mime_without_params(content_type) == "text/html"


def _domain_key(raw_url: str) -> str | None:
    try:
        host = URL(raw_url).host
        return host.lower() if host else None
    except Exception:
        return None


def _throttle_domain(domain: str, *, delay_seconds: float) -> None:
    if delay_seconds <= 0:
        return
    now = time.monotonic()
    with _domain_lock:
        last = _last_fetch_at_by_domain.get(domain)
        if last is None:
            _last_fetch_at_by_domain[domain] = now
            return
        wait = (last + delay_seconds) - now
        if wait > 0:
            # Sleep outside the lock, but reserve the slot to avoid races.
            _last_fetch_at_by_domain[domain] = last + delay_seconds
        else:
            _last_fetch_at_by_domain[domain] = now
            return
    time.sleep(wait)


def fetch_html(
    url: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> FetchHtmlSuccess | FetchHtmlFailure:
    """
    GET ``url`` and return decoded HTML or a structured failure.

    * Sync ``httpx.Client``: redirect following enabled with a max redirect count.
    * Timeout from ``crawl_request_timeout_seconds``.
    * ``User-Agent`` from ``crawl_http_user_agent`` or built-in default.
    * Only **200** responses with ``Content-Type`` MIME ``text/html`` yield success.
    * Response body size capped by ``crawl_max_response_bytes``.
    """
    raw = url.strip()
    if not raw:
        return FetchHtmlFailure(
            url=url,
            kind="invalid_url",
            reason="URL is empty",
            retry_count=0,
        )

    s = settings or get_settings()
    timeout = float(s.crawl_request_timeout_seconds)
    ua = _effective_user_agent(s)
    max_redirects = max(1, s.crawl_max_redirects)
    max_bytes = s.crawl_max_response_bytes
    domain_delay_seconds = float(s.crawl_domain_delay_seconds)

    headers = {"User-Agent": ua, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}

    retryable_http_statuses = {429, 500, 502, 503, 504}
    non_retryable_http_statuses = {400, 401, 403, 404}
    backoff_seconds = (1.0, 3.0)

    def _should_retry(failure: FetchHtmlFailure) -> bool:
        if failure.kind in {"timeout", "connect", "tls", "protocol"}:
            return True
        if failure.kind != "http_error":
            return False
        status = int(failure.status_code or 0)
        if status in retryable_http_statuses:
            return True
        if status in non_retryable_http_statuses:
            return False
        if 400 <= status < 500:
            return False
        return 500 <= status < 600

    def _execute_once(c: httpx.Client) -> FetchHtmlSuccess | FetchHtmlFailure:
        domain = _domain_key(raw)
        if domain:
            _throttle_domain(domain, delay_seconds=domain_delay_seconds)

        start = time.perf_counter()

        try:
            response = c.get(raw, headers=headers)
        except httpx.TimeoutException as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchHtmlFailure(
                url=raw,
                kind="timeout",
                reason=str(exc) or "request timed out",
                elapsed_ms=elapsed_ms,
                retry_count=0,
            )
        except httpx.TooManyRedirects as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchHtmlFailure(
                url=raw,
                kind="redirect_error",
                reason=str(exc) or "too many redirects",
                elapsed_ms=elapsed_ms,
                retry_count=0,
            )
        except httpx.ConnectError as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchHtmlFailure(
                url=raw,
                kind="connect",
                reason=str(exc) or "connection failed",
                elapsed_ms=elapsed_ms,
                retry_count=0,
            )
        except httpx.LocalProtocolError as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchHtmlFailure(
                url=raw,
                kind="protocol",
                reason=str(exc) or "protocol error",
                elapsed_ms=elapsed_ms,
                retry_count=0,
            )
        except httpx.RequestError as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            msg = str(exc) or "request failed"
            kind = "tls" if "certificate" in msg.lower() or "ssl" in msg.lower() else "connect"
            return FetchHtmlFailure(url=raw, kind=kind, reason=msg, elapsed_ms=elapsed_ms, retry_count=0)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        final_url = str(response.url)
        ct_header = response.headers.get("content-type")

        if len(response.content) > max_bytes:
            return FetchHtmlFailure(
                url=raw,
                kind="oversized",
                reason=f"response body exceeds {max_bytes} bytes",
                elapsed_ms=elapsed_ms,
                status_code=response.status_code,
                content_type=ct_header,
                retry_count=0,
            )

        if response.status_code >= 400:
            return FetchHtmlFailure(
                url=raw,
                kind="http_error",
                reason=f"HTTP {response.status_code}",
                elapsed_ms=elapsed_ms,
                status_code=response.status_code,
                content_type=ct_header,
                retry_count=0,
            )

        if response.status_code != 200:
            return FetchHtmlFailure(
                url=raw,
                kind="http_error",
                reason=f"unexpected status {response.status_code}",
                elapsed_ms=elapsed_ms,
                status_code=response.status_code,
                content_type=ct_header,
                retry_count=0,
            )

        if not _is_html_content_type(ct_header):
            return FetchHtmlFailure(
                url=raw,
                kind="not_html",
                reason="Content-Type is not text/html",
                elapsed_ms=elapsed_ms,
                status_code=response.status_code,
                content_type=ct_header,
                retry_count=0,
            )

        html = response.text
        canonical_ct = _mime_without_params(ct_header) or "text/html"

        return FetchHtmlSuccess(
            url=raw,
            final_url=final_url,
            status_code=response.status_code,
            content_type=canonical_ct,
            html=html,
            elapsed_ms=elapsed_ms,
        )

    timeout_cfg = httpx.Timeout(timeout)

    def _execute_with_retries(c: httpx.Client) -> FetchHtmlSuccess | FetchHtmlFailure:
        last: FetchHtmlSuccess | FetchHtmlFailure | None = None
        for attempt_index in range(len(backoff_seconds) + 1):
            out = _execute_once(c)
            if isinstance(out, FetchHtmlSuccess):
                return out
            last = out
            if attempt_index >= len(backoff_seconds):
                break
            if not _should_retry(out):
                break
            time.sleep(backoff_seconds[attempt_index])

        assert isinstance(last, FetchHtmlFailure)
        retries_attempted = min(attempt_index, len(backoff_seconds))
        return last.model_copy(update={"retry_count": retries_attempted})

    if client is not None:
        return _execute_with_retries(client)

    with httpx.Client(
        timeout=timeout_cfg,
        follow_redirects=True,
        max_redirects=max_redirects,
        verify=True,
    ) as c:
        return _execute_with_retries(c)
