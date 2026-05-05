"""HTML parser: title, text, and link extraction."""

from services.parse_html import ParsedPage, parse_html


def test_parse_html_basic() -> None:
    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Welcome</h1>
        <p>Hello world.</p>
        <a href="/about">About</a>
        <a href="https://example.com/contact">Contact</a>
    </body>
    </html>
    """
    result = parse_html(html, base_url="https://example.com/page")
    assert isinstance(result, ParsedPage)
    assert result.title == "Test Page"
    assert "Hello world" in result.text
    assert "Welcome" in result.text
    assert result.text_length == len(result.text)
    assert "https://example.com/about" in result.links
    assert "https://example.com/contact" in result.links


def test_parse_html_og_title_priority() -> None:
    html = """
    <html>
    <head>
        <meta property="og:title" content="OG Title Here">
        <title>Fallback Title</title>
    </head>
    <body><h1>H1 Title</h1></body>
    </html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert result.title == "OG Title Here"


def test_parse_html_title_fallback_to_title_tag() -> None:
    html = """
    <html>
    <head><title>Title Tag</title></head>
    <body><h1>H1 Title</h1></body>
    </html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert result.title == "Title Tag"


def test_parse_html_title_fallback_to_h1() -> None:
    html = """
    <html>
    <head></head>
    <body><h1>Only H1</h1></body>
    </html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert result.title == "Only H1"


def test_parse_html_title_empty_when_missing() -> None:
    html = "<html><body><p>No title here</p></body></html>"
    result = parse_html(html, base_url="https://example.com/")
    assert result.title == ""


def test_parse_html_strips_script_style() -> None:
    html = """
    <html>
    <head><title>T</title><style>body { color: red; }</style></head>
    <body>
        <script>alert('bad');</script>
        <p>Good text.</p>
        <style>.foo { }</style>
    </body>
    </html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert "alert" not in result.text
    assert "color: red" not in result.text
    assert "Good text" in result.text


def test_parse_html_strips_nav_header_footer_aside() -> None:
    html = """
    <html>
    <body>
        <header>Header nav stuff</header>
        <nav>Navigation links</nav>
        <main><p>Main content here.</p></main>
        <aside>Sidebar info</aside>
        <footer>Footer text</footer>
    </body>
    </html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert "Header nav stuff" not in result.text
    assert "Navigation links" not in result.text
    assert "Sidebar info" not in result.text
    assert "Footer text" not in result.text
    assert "Main content here" in result.text


def test_parse_html_strips_role_navigation() -> None:
    html = """
    <html>
    <body>
        <div role="navigation">Nav by role</div>
        <p>Real content.</p>
    </body>
    </html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert "Nav by role" not in result.text
    assert "Real content" in result.text


def test_parse_html_strips_nav_class_id() -> None:
    html = """
    <html>
    <body>
        <div class="main-nav">Class nav</div>
        <div id="footer-menu">ID menu</div>
        <div class="sidebar-widget">Sidebar widget</div>
        <p>Body text.</p>
    </body>
    </html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert "Class nav" not in result.text
    assert "ID menu" not in result.text
    assert "Sidebar widget" not in result.text
    assert "Body text" in result.text


def test_parse_html_relative_links_resolved() -> None:
    html = """
    <html><body>
        <a href="/absolute-path">Link 1</a>
        <a href="relative">Link 2</a>
        <a href="../up">Link 3</a>
    </body></html>
    """
    result = parse_html(html, base_url="https://example.com/dir/page")
    assert "https://example.com/absolute-path" in result.links
    assert "https://example.com/dir/relative" in result.links
    assert "https://example.com/up" in result.links


def test_parse_html_skips_mailto_tel_javascript_data() -> None:
    html = """
    <html><body>
        <a href="mailto:test@example.com">Email</a>
        <a href="tel:+1234567890">Phone</a>
        <a href="javascript:void(0)">JS</a>
        <a href="data:text/html,<h1>Hi</h1>">Data</a>
        <a href="https://example.com/valid">Valid</a>
    </body></html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert len(result.links) == 1
    assert "https://example.com/valid" in result.links


def test_parse_html_skips_fragment_only_links() -> None:
    html = """
    <html><body>
        <a href="#section">Anchor</a>
        <a href="https://example.com/page#sec">With fragment</a>
    </body></html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert "#section" not in str(result.links)
    assert "https://example.com/page" in result.links


def test_parse_html_dedupes_links_preserving_order() -> None:
    html = """
    <html><body>
        <a href="/a">First</a>
        <a href="/b">Second</a>
        <a href="/a">Duplicate</a>
        <a href="/c">Third</a>
    </body></html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert result.links == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]


def test_parse_html_normalizes_links() -> None:
    html = """
    <html><body>
        <a href="https://EXAMPLE.COM/PATH/?utm_source=x">Link</a>
    </body></html>
    """
    result = parse_html(html, base_url="https://example.com/")
    assert "https://example.com/PATH" in result.links
    assert "utm_source" not in str(result.links)


def test_parse_html_scheme_relative_link() -> None:
    html = '<html><body><a href="//cdn.example.org/resource">CDN</a></body></html>'
    result = parse_html(html, base_url="https://main.example.com/")
    assert "https://cdn.example.org/resource" in result.links


def test_parse_html_text_length_field() -> None:
    html = "<html><body><p>Exactly this text.</p></body></html>"
    result = parse_html(html, base_url="https://example.com/")
    assert result.text_length == len(result.text)
    assert result.text_length > 0
