import os

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def test_database_url() -> str:
    url = os.environ.get("CRAWLIQ_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("Set CRAWLIQ_TEST_DATABASE_URL to run database integration tests")
    return url


@pytest.fixture(autouse=True)
def _reset_database_between_integration_tests(request: pytest.FixtureRequest, test_database_url: str) -> None:
    """
    Integration tests share a real Postgres database. To keep tests independent and
    deterministic, truncate all application tables between tests.
    """
    if request.node.get_closest_marker("integration") is None:
        return

    # Ensure we use psycopg (v3) which is already a project dependency.
    url = test_database_url
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN (
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename <> 'alembic_version'
  )
  LOOP
    EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE';
  END LOOP;
END $$;
"""
            )
        )
