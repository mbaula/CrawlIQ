from models import Base

EXPECTED_TABLES = frozenset(
    {
        "crawl_jobs",
        "pages",
        "page_links",
        "crawl_errors",
        "terms",
        "inverted_index",
        "search_queries",
    },
)


def test_model_tables_match_schema() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES
