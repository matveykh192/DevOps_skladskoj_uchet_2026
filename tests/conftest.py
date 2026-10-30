"""Isolated PostgreSQL fixtures. Never touch a non-test database."""
import os
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import get_current_user
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Material, MeasurementUnit, Role, Supplier, User


def _assert_test_database():
    url = make_url(os.environ.get("DATABASE_URL", "sqlite:///missing.db"))
    assert os.environ.get("APP_ENV") == "test", "Refusing database writes outside APP_ENV=test"
    assert url.get_backend_name() == "postgresql", "Tests require PostgreSQL"
    assert url.database == "warehouse_test_db", "Refusing writes to a non-test database"
    assert url.host == "test-db", "Refusing writes outside isolated test-db container"
    return url


@pytest.fixture
async def test_session():
    """Recreate only the isolated test database schema for each integration test."""
    url = _assert_test_database()
    engine = create_async_engine(url)
    try:
        # Test schema is created from ORM metadata; real app migrations are tested separately.
        import app.models  # noqa: F401

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            yield session
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def client(test_session):
    async def override_db():
        yield test_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://testserver") as http:
            yield http
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def seeded(client, test_session):
    role = Role(name="admin")
    unit = MeasurementUnit(name="Штука", short_name="шт", is_active=True)
    supplier = Supplier(name="Тестовый поставщик", is_active=True)
    test_session.add_all([role, unit, supplier])
    await test_session.flush()
    user = User(username="tester", password_hash="not-used-in-overridden-auth", role_id=role.id, is_active=True)
    material = Material(name="Тестовый болт", measurement_unit_id=unit.id, quantity=Decimal("0"), is_active=True)
    test_session.add_all([user, material])
    await test_session.commit()
    fastapi_app.dependency_overrides[get_current_user] = lambda: user
    return {
        "user": user,
        "unit": unit,
        "supplier": supplier,
        "material": material,
        "date": date(2026, 10, 14).isoformat(),
    }
