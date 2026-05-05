import os

import pytest


@pytest.fixture
def test_database_url() -> str:
    url = os.environ.get("CRAWLIQ_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("Set CRAWLIQ_TEST_DATABASE_URL to run database integration tests")
    return url
