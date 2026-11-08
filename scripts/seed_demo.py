"""Idempotent local learning database bootstrap. Requires DEMO_ADMIN_PASSWORD."""

import asyncio
import os

import bcrypt
from sqlalchemy import text
from app.database import engine


async def main():
    password = os.environ.get("DEMO_ADMIN_PASSWORD", "")
    if len(password) < 8:
        raise SystemExit("Set DEMO_ADMIN_PASSWORD (at least 8 characters) before running this script")
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    async with engine.begin() as conn:
        role_id = (await conn.execute(text("""
            INSERT INTO roles (name) VALUES ('admin')
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """))).scalar_one()
        await conn.execute(text("""
            INSERT INTO roles (name) VALUES ('warehouse_worker')
            ON CONFLICT (name) DO NOTHING
        """))
        for name, short in (("Штука", "шт."), ("Килограмм", "кг"), ("Метр", "м")):
            await conn.execute(text("""
                INSERT INTO measurement_units (name, short_name)
                VALUES (:name, :short)
                ON CONFLICT (name) DO NOTHING
            """), {"name": name, "short": short})
        await conn.execute(text("""
            INSERT INTO users (username, password_hash, role_id, is_active)
            VALUES ('admin', :password_hash, :role_id, TRUE)
            ON CONFLICT (username) DO UPDATE SET
              password_hash = EXCLUDED.password_hash,
              role_id = EXCLUDED.role_id,
              is_active = TRUE
        """), {"password_hash": password_hash, "role_id": role_id})
    await engine.dispose()
    print("Seed complete: admin user, roles and measurement units are ready")


if __name__ == "__main__":
    asyncio.run(main())
