"""Test Alembic on TWO expendable isolated databases; never touch app DB."""
import asyncio
import os
import subprocess
import sys
from decimal import Decimal

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine import make_url

from app.database import Base
from app.models import Material, MeasurementUnit, Supplier, Role

DB_NAMES = ("warehouse_migration_clean", "warehouse_migration_filled")


def guarded_url():
    url = make_url(os.environ.get("DATABASE_URL", ""))
    if os.environ.get("APP_ENV") != "test" or url.host != "test-db" or url.database != "warehouse_test_db":
        raise RuntimeError("Migrations check may only run on isolated warehouse_test_db at test-db")
    return url


def run_alembic(target, *args):
    env = os.environ.copy()
    env["DATABASE_URL"] = target
    subprocess.run([sys.executable, "-m", "alembic", "-c", "alembic.ini", *args], check=True, env=env)


async def create_databases(url):
    admin = await asyncpg.connect(host=url.host, port=url.port or 5432, user=url.username, password=url.password, database="postgres")
    try:
        for db in DB_NAMES:
            await admin.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
            await admin.execute(f'CREATE DATABASE "{db}"')
    finally:
        await admin.close()


async def check():
    base = guarded_url()
    await create_databases(base)
    clean = base.set(database=DB_NAMES[0]).render_as_string(hide_password=False)
    filled = base.set(database=DB_NAMES[1]).render_as_string(hide_password=False)
    # Empty database: migrate across all three steps.
    run_alembic(clean, "upgrade", "head")
    engine = create_async_engine(clean)
    try:
        async with engine.connect() as conn:
            tables = (await conn.exec_driver_sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('materials','issues','receipts')")).scalar_one()
            assert tables == 3, "Baseline tables missing"
            row = (await conn.exec_driver_sql("SELECT version_num FROM alembic_version")).scalar_one()
            assert row == "003_minimum_stock"
    finally:
        await engine.dispose()
    print("PASS: clean DB upgraded 001 -> 002 -> 003", flush=True)

    # Filled database: reproduce existing ORM schema, seed rows, validate baseline, then stamp.
    engine = create_async_engine(filled)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            unit = MeasurementUnit(name="До миграции", short_name="дм")
            role = Role(name="admin")
            supplier = Supplier(name="Поставщик до миграции")
            session.add_all([unit, role, supplier])
            await session.flush()
            material = Material(name="Контрольный материал", measurement_unit_id=unit.id, quantity=Decimal("12.500"))
            session.add(material)
            await session.commit()
            original_id = material.id
        # Current ORM already contains the column added by revision 003.
        # Reproduce the PRE-003 schema in this disposable, dedicated test DB.
        # This must happen only after inserting the control material, so we
        # also exercise preservation of pre-existing data during the upgrade.
        async with engine.begin() as conn:
            await conn.exec_driver_sql("ALTER TABLE materials DROP COLUMN minimum_stock")
            remaining = (await conn.execute(text(
                "SELECT COUNT(*) FROM materials WHERE id = :id AND quantity = :qty"
            ), {"id": original_id, "qty": Decimal("12.500")})).scalar_one()
            assert remaining == 1, "Control material disappeared while preparing legacy schema"
            col_count = (await conn.exec_driver_sql(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='materials' AND column_name='minimum_stock'"
            )).scalar_one()
            assert col_count == 0, "Legacy schema must not yet contain minimum_stock"
    finally:
        await engine.dispose()
    # Explicit stamp only on a known, verified, migration-test schema.
    run_alembic(filled, "stamp", "001_baseline")
    run_alembic(filled, "upgrade", "head")
    engine = create_async_engine(filled)
    try:
        async with engine.connect() as conn:
            row = (await conn.execute(text("SELECT id, name, quantity, minimum_stock FROM materials WHERE id = :id"), {"id": original_id})).one()
            assert row.name == "Контрольный материал"
            assert row.quantity == Decimal("12.500")
            assert row.minimum_stock == Decimal("0")
            version = (await conn.exec_driver_sql("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "003_minimum_stock"
    finally:
        await engine.dispose()
    print("PASS: filled DB preserved material and quantity, added minimum_stock", flush=True)
    print("MIGRATION CHECKS PASSED", flush=True)


if __name__ == "__main__":
    asyncio.run(check())
