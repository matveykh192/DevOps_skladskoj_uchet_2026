"""Minimal isolated checks for the LR3 test harness.

Business-rule coverage and the 60% threshold will be introduced in stage 2.
"""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def test_test_database_is_isolated():
    """Never allow testing against the default application database."""
    url = os.environ.get("DATABASE_URL", "")
    assert "warehouse_test_db" in url
    assert "test-db" in url
    assert os.environ.get("APP_ENV") == "test"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_postgresql_is_reachable():
    url = os.environ["DATABASE_URL"]
    assert "warehouse_test_db" in url
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT current_database()"))
            assert result.scalar_one() == "warehouse_test_db"
    finally:
        await engine.dispose()
