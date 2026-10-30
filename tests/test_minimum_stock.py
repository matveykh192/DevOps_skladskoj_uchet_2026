"""LR3: per-material minimum stock is advisory, never a blocker."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Material

pytestmark = pytest.mark.integration


async def test_default_minimum_is_zero(client, seeded):
    response = await client.get(f"/materials/{seeded['material'].id}")
    assert response.status_code == 200
    assert response.json()["minimum_stock"] == 0
    assert response.json()["is_below_minimum"] is False


async def test_create_with_minimum(client, seeded):
    response = await client.post(
        "/materials/",
        json={
            "name": "Складской тестовый материал C",
            "measurement_unit_id": seeded["unit"].id,
            "minimum_stock": 10.5,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["minimum_stock"] == 10.5
    assert data["is_below_minimum"] is True
    listing = (await client.get("/materials/")).json()
    item = next(m for m in listing if m["id"] == data["id"])
    assert item["is_below_minimum"] is True


async def test_update_minimum_changes_warning(client, seeded):
    material_id = seeded["material"].id
    changed = await client.put(f"/materials/{material_id}", json={"minimum_stock": 5})
    assert changed.status_code == 200, changed.text
    assert changed.json()["is_below_minimum"] is True
    changed = await client.put(f"/materials/{material_id}", json={"minimum_stock": 0})
    assert changed.status_code == 200, changed.text
    assert changed.json()["is_below_minimum"] is False


@pytest.mark.parametrize("invalid", [-1, -0.001, 1000000000, "not-a-number"])
async def test_invalid_minimum_rejected(client, seeded, invalid):
    response = await client.put(f"/materials/{seeded['material'].id}", json={"minimum_stock": invalid})
    assert response.status_code == 422, response.text


async def test_boundary_exactly_equal_is_not_low(client, seeded, test_session):
    material = seeded["material"]
    material.quantity = Decimal("5.000")
    material.minimum_stock = Decimal("5.000")
    await test_session.commit()
    equal = await client.get(f"/materials/{material.id}")
    assert equal.json()["is_below_minimum"] is False
    material.quantity = Decimal("4.999")
    await test_session.commit()
    low = await client.get(f"/materials/{material.id}")
    assert low.json()["is_below_minimum"] is True
    stored = (await test_session.execute(select(Material).where(Material.id == material.id))).scalar_one()
    assert stored.minimum_stock == Decimal("5.000")


async def test_old_low_stock_report_keeps_manual_threshold(client, seeded, test_session):
    material = seeded["material"]
    material.quantity = Decimal("12.000")
    material.minimum_stock = Decimal("15.000")
    await test_session.commit()
    response = await client.get("/materials/low-stock?threshold=10")
    assert response.status_code == 200
    assert response.json()["count"] == 0
    listing = await client.get("/materials/")
    item = next(m for m in listing.json() if m["id"] == material.id)
    assert item["is_below_minimum"] is True
