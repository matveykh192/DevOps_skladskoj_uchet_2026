"""Fast, database-independent tests for input rules and JWT/password utilities."""
from datetime import timedelta

import pytest
from jose import jwt
from pydantic import ValidationError

from app.auth import create_access_token, get_password_hash, verify_password
from app.config import settings
from app.routers.issues import IssueCreate, IssueItemInput
from app.routers.receipts import ReceiptCreate, ReceiptItemInput
from app.schemas import MaterialCreate, MaterialUpdate, SupplierCreate


@pytest.mark.unit
def test_password_hash_round_trip():
    hashed = get_password_hash("safe-test-password")
    assert hashed != "safe-test-password"
    assert verify_password("safe-test-password", hashed)
    assert not verify_password("wrong-password", hashed)


@pytest.mark.unit
def test_token_has_username_and_expiration():
    token = create_access_token({"sub": "tester"}, timedelta(minutes=5))
    claims = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    assert claims["sub"] == "tester"
    assert "exp" in claims


@pytest.mark.unit
@pytest.mark.parametrize("quantity", [0, -1, -0.01])
def test_receipt_rejects_nonpositive_quantity(quantity):
    with pytest.raises(ValidationError):
        ReceiptItemInput(material_name="Болт", quantity=quantity, unit_price=10)


@pytest.mark.unit
@pytest.mark.parametrize("price", [-1, -0.01])
def test_receipt_rejects_negative_price(price):
    with pytest.raises(ValidationError):
        ReceiptItemInput(material_name="Болт", quantity=1, unit_price=price)


@pytest.mark.unit
def test_receipt_accepts_zero_price():
    assert ReceiptItemInput(material_name="Болт", quantity=1, unit_price=0).unit_price == 0


@pytest.mark.unit
@pytest.mark.parametrize("quantity", [0, -1, -0.001])
def test_issue_rejects_nonpositive_quantity(quantity):
    with pytest.raises(ValidationError):
        IssueItemInput(material_id=1, quantity=quantity)


@pytest.mark.unit
def test_document_number_is_required():
    with pytest.raises(ValidationError):
        ReceiptCreate(receipt_number="", receipt_date="2026-10-14", items=[])
    with pytest.raises(ValidationError):
        IssueCreate(issue_number="", department="Цех", issue_date="2026-10-14", items=[])


@pytest.mark.unit
def test_material_rejects_invalid_measurement_unit_id():
    with pytest.raises(ValidationError):
        MaterialCreate(name="Болт", measurement_unit_id=0)
    with pytest.raises(ValidationError):
        MaterialUpdate(measurement_unit_id=-3)


@pytest.mark.unit
def test_material_rejects_name_too_long():
    with pytest.raises(ValidationError):
        MaterialCreate(name="x" * 256, measurement_unit_id=1)


@pytest.mark.unit
def test_supplier_input_accepts_contact_fields():
    supplier = SupplierCreate(name="Поставщик", phone="+7-900-000-00-00")
    assert supplier.phone == "+7-900-000-00-00"
