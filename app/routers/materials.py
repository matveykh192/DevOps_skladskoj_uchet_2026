from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import Material, ReceiptItem, IssueItem, User
from app.schemas import MaterialCreate, MaterialUpdate, MaterialResponse
from app.auth import get_current_user

router = APIRouter(prefix="/materials", tags=["Materials"])


@router.get("/")
async def get_materials(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Material).where(Material.is_active == True).order_by(Material.name)
    )
    materials = result.scalars().all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "measurement_unit_id": m.measurement_unit_id,
            "description": m.description or "",
            "is_active": m.is_active,
            "quantity": float(m.quantity or 0)
        }
        for m in materials
    ]


@router.get("/low-stock")
async def get_low_stock(threshold: float = 10.0, db: AsyncSession = Depends(get_db)):
    """Материалы с остатком ниже заданного порога (по умолчанию — 10)."""
    result = await db.execute(
        select(Material)
        .where(Material.is_active == True)
        .where(Material.quantity < threshold)
        .order_by(Material.quantity.asc())
    )
    materials = result.scalars().all()

    return {
        "threshold": threshold,
        "count": len(materials),
        "items": [
            {
                "id": m.id,
                "name": m.name,
                "measurement_unit_id": m.measurement_unit_id,
                "description": m.description or "",
                "quantity": float(m.quantity or 0)
            }
            for m in materials
        ]
    }


@router.get("/{material_id}", response_model=MaterialResponse)
async def get_material(material_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Material).where(Material.id == material_id))
    material = result.scalars().first()
    if not material or not material.is_active:
        raise HTTPException(status_code=404, detail="материал не найден")
    return material


@router.post("/", response_model=MaterialResponse, status_code=201)
async def create_material(material: MaterialCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Material).where(Material.name == material.name))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="такой материал уже есть")
    new_material = Material(**material.model_dump(), quantity=0)
    db.add(new_material)
    await db.commit()
    await db.refresh(new_material)
    return new_material


@router.put("/{material_id}", response_model=MaterialResponse)
async def update_material(material_id: int, material_data: MaterialUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Material).where(Material.id == material_id))
    material = result.scalars().first()
    if not material:
        raise HTTPException(status_code=404, detail="материал не найден")

    update_data = material_data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != material.name:
        check = await db.execute(select(Material).where(Material.name == update_data["name"]))
        if check.scalars().first():
            raise HTTPException(status_code=400, detail="материал с таким названием уже есть")

    for key, value in update_data.items():
        setattr(material, key, value)

    await db.commit()
    await db.refresh(material)
    return material


@router.delete("/{material_id}")
async def delete_material(material_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Material).where(Material.id == material_id))
    material = result.scalars().first()
    if not material:
        raise HTTPException(status_code=404, detail="материал не найден")

    rc = await db.execute(select(func.count()).select_from(ReceiptItem).where(ReceiptItem.material_id == material_id))
    ic = await db.execute(select(func.count()).select_from(IssueItem).where(IssueItem.material_id == material_id))
    if (rc.scalar() or 0) + (ic.scalar() or 0) > 0:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить материал, у которого есть история движений. Сначала удалите связанные документы."
        )

    await db.delete(material)
    await db.commit()
    return {"message": "Материал удалён"}