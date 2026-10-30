"""Business behavior with real, dedicated PostgreSQL and FastAPI HTTP routes."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Issue, Receipt, ReceiptItem

pytestmark = pytest.mark.integration


def receipt_payload(number="R-001", quantity=10, price=12.5):
    return {
        "receipt_number": number,
        "supplier_name": "Тестовый поставщик",
        "receipt_date": "2026-10-14",
        "items": [
            {"material_name": "Тестовый болт", "measurement_unit_id": 1, "quantity": quantity, "unit_price": price}
        ],
    }


def issue_payload(number="I-001", material_id=1, quantity=5):
    return {
        "issue_number": number,
        "department": "Цех",
        "issue_date": "2026-10-14",
        "items": [{"material_id": material_id, "quantity": quantity}],
    }


async def test_material_listing(client, seeded):
    response = await client.get("/materials/")
    assert response.status_code == 200
    assert any(item["name"] == "Тестовый болт" for item in response.json())


async def test_create_material_and_duplicate(client, seeded):
    data = {"name": "Шайба", "measurement_unit_id": seeded["unit"].id}
    created = await client.post("/materials/", json=data)
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Шайба"
    assert (await client.post("/materials/", json=data)).status_code == 400


async def test_update_material(client, seeded):
    material_id = seeded["material"].id
    response = await client.put(f"/materials/{material_id}", json={"description": "Проверено"})
    assert response.status_code == 200
    assert response.json()["description"] == "Проверено"


async def test_missing_material(client, seeded):
    assert (await client.get("/materials/987654")).status_code == 404


async def test_material_validation(client, seeded):
    response = await client.post("/materials/", json={"name": "Ошибка", "measurement_unit_id": 0})
    assert response.status_code == 422


async def test_supplier_creation_and_duplicate(client, seeded):
    payload = {"name": "Новый поставщик", "phone": "123"}
    assert (await client.post("/suppliers/", json=payload)).status_code == 201
    assert (await client.post("/suppliers/", json=payload)).status_code == 400


async def test_supplier_soft_delete(client, seeded):
    sid = seeded["supplier"].id
    result = await client.delete(f"/suppliers/{sid}")
    assert result.status_code == 200
    assert (await client.get(f"/suppliers/{sid}")).status_code == 404
    assert not any(s["id"] == sid for s in (await client.get("/suppliers/")).json())


async def test_receipt_increases_balance(client, seeded, test_session):
    response = await client.post("/receipts/", json=receipt_payload())
    assert response.status_code == 201, response.text
    await test_session.refresh(seeded["material"])
    assert seeded["material"].quantity == Decimal("10.000")
    listing = await client.get("/receipts/")
    assert listing.status_code == 200
    assert listing.json()[0]["total_amount"] == 125.0


async def test_receipt_with_zero_price_is_allowed(client, seeded):
    response = await client.post("/receipts/", json=receipt_payload(price=0))
    assert response.status_code == 201, response.text


async def test_receipt_duplicate_number_is_rejected(client, seeded):
    assert (await client.post("/receipts/", json=receipt_payload())).status_code == 201
    assert (await client.post("/receipts/", json=receipt_payload())).status_code == 400


async def test_receipt_negative_quantity_rejected(client, seeded):
    response = await client.post("/receipts/", json=receipt_payload(quantity=-1))
    assert response.status_code == 422


async def test_receipt_deletion_reverses_balance(client, seeded, test_session):
    response = await client.post("/receipts/", json=receipt_payload())
    assert response.status_code == 201
    rid = response.json()["id"]
    deleted = await client.delete(f"/receipts/{rid}")
    assert deleted.status_code == 200
    await test_session.refresh(seeded["material"])
    assert seeded["material"].quantity == Decimal("0.000")


async def test_issue_exact_available_balance_is_allowed(client, seeded, test_session):
    assert (await client.post("/receipts/", json=receipt_payload(quantity=10))).status_code == 201
    response = await client.post("/issues/", json=issue_payload(quantity=10))
    assert response.status_code == 201, response.text
    await test_session.refresh(seeded["material"])
    assert seeded["material"].quantity == Decimal("0.000")


async def test_issue_above_available_balance_is_rejected(client, seeded, test_session):
    assert (await client.post("/receipts/", json=receipt_payload(quantity=10))).status_code == 201
    response = await client.post("/issues/", json=issue_payload(quantity=11))
    assert response.status_code == 400
    await test_session.refresh(seeded["material"])
    assert seeded["material"].quantity == Decimal("10.000")
    assert (await test_session.execute(select(Issue))).scalars().first() is None


async def test_issue_without_stock_is_rejected(client, seeded):
    response = await client.post("/issues/", json=issue_payload(quantity=1))
    assert response.status_code == 400


async def test_issue_missing_material_is_rejected(client, seeded):
    response = await client.post("/issues/", json=issue_payload(material_id=99999))
    assert response.status_code == 404


async def test_issue_deletion_restores_balance(client, seeded, test_session):
    assert (await client.post("/receipts/", json=receipt_payload(quantity=10))).status_code == 201
    response = await client.post("/issues/", json=issue_payload(quantity=4))
    assert response.status_code == 201, response.text
    await test_session.refresh(seeded["material"])
    assert seeded["material"].quantity == Decimal("6.000")
    assert (await client.delete(f"/issues/{response.json()['id']}")).status_code == 200
    await test_session.refresh(seeded["material"])
    assert seeded["material"].quantity == Decimal("10.000")


async def test_issue_duplicate_number_is_rejected(client, seeded):
    assert (await client.post("/receipts/", json=receipt_payload())).status_code == 201
    assert (await client.post("/issues/", json=issue_payload(quantity=1))).status_code == 201
    assert (await client.post("/issues/", json=issue_payload(quantity=1))).status_code == 400


async def test_postgresql_relationships_are_persisted(client, seeded, test_session):
    response = await client.post("/receipts/", json=receipt_payload())
    assert response.status_code == 201
    receipt = (await test_session.execute(select(Receipt))).scalars().first()
    item = (await test_session.execute(select(ReceiptItem))).scalars().first()
    assert receipt.supplier_id == seeded["supplier"].id
    assert item.receipt_id == receipt.id
    assert item.material_id == seeded["material"].id


async def test_cannot_delete_material_with_receipt_history(client, seeded):
    assert (await client.post("/receipts/", json=receipt_payload())).status_code == 201
    response = await client.delete(f"/materials/{seeded['material'].id}")
    assert response.status_code == 400


async def test_low_stock_filter(client, seeded):
    response = await client.get("/materials/low-stock?threshold=10")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["name"] == "Тестовый болт"
