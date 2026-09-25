from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from app.database import get_db
from app.models import Receipt, ReceiptItem, Material, Supplier, User
from app.auth import get_current_user
from pydantic import BaseModel, Field
from typing import List

router = APIRouter(prefix="/receipts", tags=["Receipts"])


class ReceiptItemInput(BaseModel):
    material_name: str = Field(..., min_length=1)
    measurement_unit_id: int = 1
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)


class ReceiptCreate(BaseModel):
    receipt_number: str = Field(..., min_length=1, max_length=50)
    supplier_name: str = "Основной поставщик"
    receipt_date: str
    items: List[ReceiptItemInput]


@router.get("/")
async def get_receipts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Receipt).order_by(Receipt.id.desc()))
    receipts = result.scalars().all()

    output = []
    for r in receipts:
        items_result = await db.execute(
            select(ReceiptItem, Material.name)
            .join(Material, ReceiptItem.material_id == Material.id)
            .where(ReceiptItem.receipt_id == r.id)
        )
        items = items_result.all()

        total_amount = sum(
            float(item[0].quantity) * float(item[0].unit_price) for item in items
        )

        output.append({
            "id": r.id,
            "receipt_number": r.receipt_number,
            "supplier_id": r.supplier_id,
            "receipt_date": r.receipt_date.isoformat() if r.receipt_date else "",
            "status": r.status,
            "total_amount": total_amount,
            "items": [
                {
                    "id": item[0].id,
                    "material_id": item[0].material_id,
                    "material_name": item[1],
                    "quantity": float(item[0].quantity),
                    "unit_price": float(item[0].unit_price),
                    "line_total": float(item[0].quantity) * float(item[0].unit_price)
                }
                for item in items
            ]
        })

    return output


@router.post("/", status_code=201)
async def create_receipt(
    data: ReceiptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not data.receipt_number or not data.receipt_number.strip():
        raise HTTPException(status_code=400, detail="Номер документа обязателен")

    result = await db.execute(
        select(Receipt).where(Receipt.receipt_number == data.receipt_number)
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="документ с таким номером уже есть")

    result = await db.execute(
        select(Supplier).where(Supplier.name == data.supplier_name)
    )
    supplier = result.scalars().first()
    if not supplier:
        supplier = Supplier(name=data.supplier_name, is_active=True)
        db.add(supplier)
        await db.flush()

    new_receipt = Receipt(
        receipt_number=data.receipt_number.strip(),
        supplier_id=supplier.id,
        receipt_date=datetime.strptime(data.receipt_date, "%Y-%m-%d").date(),
        status="registered",
        created_by=current_user.id
    )
    db.add(new_receipt)
    await db.flush()

    for item_data in data.items:
        material_name = item_data.material_name.strip()
        if not material_name:
            raise HTTPException(status_code=400, detail="Название материала не может быть пустым")

        result = await db.execute(select(Material).where(Material.name == material_name))
        material = result.scalars().first()
        if not material:
            material = Material(
                name=material_name,
                measurement_unit_id=item_data.measurement_unit_id,
                is_active=True,
                quantity=0
            )
            db.add(material)
            await db.flush()

        db.add(ReceiptItem(
            receipt_id=new_receipt.id,
            material_id=material.id,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price
        ))
        material.quantity = float(material.quantity or 0) + float(item_data.quantity)

    await db.commit()
    return {"message": "Поступление оформлено", "id": new_receipt.id}


@router.delete("/{receipt_id}")
async def delete_receipt(
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Receipt).where(Receipt.id == receipt_id))
    receipt = result.scalars().first()
    if not receipt:
        raise HTTPException(status_code=404, detail="поступление не найдено")

    # откатываем остатки по материалам
    items_result = await db.execute(
        select(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id)
    )
    items = items_result.scalars().all()

    for item in items:
        mat_result = await db.execute(select(Material).where(Material.id == item.material_id))
        material = mat_result.scalars().first()
        if material:
            material.quantity = float(material.quantity or 0) - float(item.quantity)
            # не даём уйти в минус — на всякий случай
            if material.quantity < 0:
                material.quantity = 0

    # удаляем сам документ (позиции удалятся каскадно)
    await db.delete(receipt)
    await db.commit()

    return {"message": "Поступление удалено"}