"""HTTP evidence for requirements F01, F09 and F13 from LR1 TZ.

The database and HTTP client are isolated by tests/conftest.py.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.auth import get_password_hash
from app.models import Material, ReceiptItem

pytestmark = pytest.mark.integration


async def test_f01_login_accepts_valid_password_and_rejects_invalid(client, seeded, test_session):
    """F01: real HTTP authentication uses database password hash."""
    seeded["user"].password_hash = get_password_hash("ValidSecret123!")
    await test_session.commit()

    ok = await client.post("/auth/login", data={"username": "tester", "password": "ValidSecret123!"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["token_type"] == "bearer"
    assert isinstance(ok.json()["access_token"], str)
    assert ok.json()["access_token"]

    incorrect = await client.post("/auth/login", data={"username": "tester", "password": "incorrect"})
    assert incorrect.status_code == 401

    unknown = await client.post("/auth/login", data={"username": "missing", "password": "ValidSecret123!"})
    assert unknown.status_code == 401


async def test_f01_rejects_inactive_user(client, seeded, test_session):
    seeded["user"].password_hash = get_password_hash("ValidSecret123!")
    seeded["user"].is_active = False
    await test_session.commit()

    response = await client.post("/auth/login", data={"username": "tester", "password": "ValidSecret123!"})
    assert response.status_code == 401


async def test_f01_protected_operation_requires_token(client):
    """No seeded fixture: get_current_user is not overridden in this test."""
    response = await client.post(
        "/receipts/",
        json={
            "receipt_number": "AUTH-PROBE",
            "receipt_date": "2026-10-14",
            "items": [],
        },
    )
    assert response.status_code == 401


async def test_f09_receipt_sums_two_lines_and_updates_two_balances(client, seeded, test_session):
    """F09: total must equal the sum of distinct quantity * unit_price lines."""
    payload = {
        "receipt_number": "TWO-LINES-001",
        "supplier_name": "Тестовый поставщик",
        "receipt_date": "2026-10-14",
        "items": [
            {
                "material_name": "Тестовый болт",
                "measurement_unit_id": seeded["unit"].id,
                "quantity": 3,
                "unit_price": 12.5,
            },
            {
                "material_name": "Тестовая гайка",
                "measurement_unit_id": seeded["unit"].id,
                "quantity": 4,
                "unit_price": 2.25,
            },
        ],
    }
    created = await client.post("/receipts/", json=payload)
    assert created.status_code == 201, created.text

    listing = await client.get("/receipts/")
    assert listing.status_code == 200, listing.text
    receipt = next(item for item in listing.json() if item["id"] == created.json()["id"])
    assert len(receipt["items"]) == 2
    subtotals = {item["material_name"]: Decimal(str(item["line_total"])) for item in receipt["items"]}
    assert subtotals == {
        "Тестовый болт": Decimal("37.5"),
        "Тестовая гайка": Decimal("9.0"),
    }
    assert Decimal(str(receipt["total_amount"])) == Decimal("46.5")

    stored_lines = (await test_session.execute(select(ReceiptItem))).scalars().all()
    assert len(stored_lines) == 2
    materials = (await test_session.execute(select(Material))).scalars().all()
    balances = {material.name: material.quantity for material in materials}
    assert balances["Тестовый болт"] == Decimal("3.000")
    assert balances["Тестовая гайка"] == Decimal("4.000")


async def test_f13_health_endpoint_reports_connected_database(client, seeded):
    """F13: HTTP health probes PostgreSQL, not merely an ASGI process."""
    response = await client.get("/health")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["database"] == "connected"
    assert payload["version"]
