import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from db.url import sync_engine_url
from models import CrawlJob


@pytest.mark.integration
def test_database_connect_select_one(test_database_url: str) -> None:
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1


@pytest.mark.integration
def test_orm_session_compiles_against_live_schema(test_database_url: str) -> None:
    """Runs a trivial ORM select (no rows required) against migrated Postgres."""
    engine = create_engine(sync_engine_url(test_database_url), pool_pre_ping=True)
    with Session(bind=engine) as session:
        session.execute(select(CrawlJob.id).limit(1))
