import httpx

from services.robots import RobotsRules, fetch_robots_txt, parse_robots_txt


def test_parse_robots_txt_user_agent_star_disallow() -> None:
    rules = parse_robots_txt(
        """
User-agent: *
Disallow: /private
Disallow: /admin/
""",
    )
    assert isinstance(rules, RobotsRules)
    assert rules.is_allowed("https://example.com/") is True
    assert rules.is_allowed("https://example.com/private") is False
    assert rules.is_allowed("https://example.com/private/x") is False
    assert rules.is_allowed("https://example.com/admin/") is False


def test_parse_robots_txt_ignores_non_star_groups() -> None:
    rules = parse_robots_txt(
        """
User-agent: BadBot
Disallow: /

User-agent: *
Disallow: /ok-nope
""",
    )
    assert rules.is_allowed("https://example.com/") is True
    assert rules.is_allowed("https://example.com/ok-nope") is False


def test_fetch_robots_txt_404_allows_all() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(404, content=b"missing")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rules = fetch_robots_txt(url="https://example.com/a", http_client=client)
    assert rules.is_allowed("https://example.com/any") is True

