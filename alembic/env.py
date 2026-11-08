"""Alembic for PostgreSQL/asyncpg. URL is supplied by environment, never saved."""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.database import Base
import app.models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be explicitly set for migrations")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Alembic migrations require PostgreSQL")
    # Alembic --stamp/upgrade to real DB requires an explicit operator choice.
    if os.environ.get("APP_ENV") != "test" and os.environ.get("WAREHOUSE_ALLOW_MIGRATE") != "YES_I_HAVE_A_BACKUP":
        raise RuntimeError("Refusing non-test migration without WAREHOUSE_ALLOW_MIGRATE=YES_I_HAVE_A_BACKUP")
    return url


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    engine = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline SQL migrations are not supported; use a verified database")
else:
    asyncio.run(run_async_migrations())
