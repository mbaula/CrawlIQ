"""Minimal robots.txt support (User-agent: * + Disallow rules)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from yarl import URL


@dataclass(frozen=True)
class RobotsRules:
    disallow_prefixes: tuple[str, ...] = ()

    def is_allowed(self, url: str) -> bool:
        try:
            path = URL(url).path or "/"
        except Exception:
            return True
        for prefix in self.disallow_prefixes:
            if prefix == "/":
                return False
            if path.startswith(prefix):
                return False
        return True


def parse_robots_txt(text: str) -> RobotsRules:
    """
    Parse robots.txt for the ``User-agent: *`` group only.

    MVP rules:
    - Only ``Disallow: <path>`` is honored
    - Empty Disallow means allow all
    - ``Allow`` is ignored for now
    """
    lines = [ln.strip() for ln in (text or "").splitlines()]

    in_star_group = False
    disallow: list[str] = []

    for raw in lines:
        if not raw or raw.startswith("#"):
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            continue
        k = key.strip().casefold()
        v = value.strip()

        if k == "user-agent":
            agent = v.casefold()
            in_star_group = agent == "*"
            continue

        if not in_star_group:
            continue

        if k == "disallow":
            if not v:
                continue
            if not v.startswith("/"):
                v = f"/{v}"
            disallow.append(v)

    # Longest prefixes first makes it easier to extend later.
    disallow_sorted = tuple(sorted(set(disallow), key=len, reverse=True))
    return RobotsRules(disallow_prefixes=disallow_sorted)


def fetch_robots_txt(
    *,
    url: str,
    http_client: httpx.Client,
    timeout_seconds: float = 10.0,
) -> RobotsRules:
    """
    Fetch and parse robots.txt for the URL's domain.

    If robots.txt is missing or cannot be fetched, default to allow-all.
    """
    try:
        u = URL(url)
        if not u.host:
            return RobotsRules()
        robots_url = str(u.with_path("/robots.txt").with_query(None).with_fragment(None))
    except Exception:
        return RobotsRules()

    try:
        resp = http_client.get(robots_url, timeout=timeout_seconds)
    except Exception:
        return RobotsRules()

    if resp.status_code == 404:
        return RobotsRules()
    if resp.status_code >= 400:
        return RobotsRules()

    return parse_robots_txt(resp.text)

