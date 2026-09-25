from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from app.database import get_db
from app.models import Issue, IssueItem, Material, User
from app.auth import get_current_user
from pydantic import BaseModel, Field
from typing import List

router = APIRouter(prefix="/issues", tags=["Issues"])


class IssueItemInput(BaseModel):
    material_id: int
    quantity: float = Field(..., gt=0)


class IssueCreate(BaseModel):
    issue_number: str = Field(..., min_length=1, max_length=50)
    department: str = Field(..., min_length=1, max_length=255)
    issue_date: str
    items: List[IssueItemInput]


@router.get("/")
async def get_issues(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Issue).order_by(Issue.id.desc()))
    issues = result.scalars().all()

    output = []
    for i in issues:
        items_result = await db.execute(
            select(IssueItem, Material.name)
            .join(Material, IssueItem.material_id == Material.id)
            .where(IssueItem.issue_id == i.id)
        )
        items = items_result.all()

        output.append({
            "id": i.id,
            "issue_number": i.issue_number,
            "department": i.department or "",
            "issue_date": i.issue_date.isoformat() if i.issue_date else "",
            "status": i.status,
            "items": [
                {
                    "id": item[0].id,
                    "material_id": item[0].material_id,
                    "material_name": item[1],
                    "quantity": float(item[0].quantity)
                }
                for item in items
            ]
        })

    return output


@router.post("/", status_code=201)
async def create_issue(
    data: IssueCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not data.issue_number or not data.issue_number.strip():
        raise HTTPException(status_code=400, detail="Номер документа обязателен")

    result = await db.execute(select(Issue).where(Issue.issue_number == data.issue_number))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="документ с таким номером уже есть")

    materials_to_update = []
    for item in data.items:
        result = await db.execute(select(Material).where(Material.id == item.material_id))
        material = result.scalars().first()
        if not material or not material.is_active:
            raise HTTPException(status_code=404, detail=f"Материал id={item.material_id} не найден")

        current_qty = float(material.quantity or 0)
        if current_qty < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно материала «{material.name}». "
                       f"Остаток: {current_qty}, запрошено: {item.quantity}"
            )
        materials_to_update.append((material, item.quantity))

    new_issue = Issue(
        issue_number=data.issue_number.strip(),
        department=data.department.strip(),
        issue_date=datetime.strptime(data.issue_date, "%Y-%m-%d").date(),
        status="registered",
        created_by=current_user.id
    )
    db.add(new_issue)
    await db.flush()

    for material, qty in materials_to_update:
        db.add(IssueItem(
            issue_id=new_issue.id,
            material_id=material.id,
            quantity=qty
        ))
        material.quantity = float(material.quantity or 0) - float(qty)

    await db.commit()
    return {"message": "Расход оформлен", "id": new_issue.id}


@router.delete("/{issue_id}")
async def delete_issue(
    issue_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalars().first()
    if not issue:
        raise HTTPException(status_code=404, detail="расход не найден")

    # возвращаем материалы обратно на склад
    items_result = await db.execute(
        select(IssueItem).where(IssueItem.issue_id == issue_id)
    )
    items = items_result.scalars().all()

    for item in items:
        mat_result = await db.execute(select(Material).where(Material.id == item.material_id))
        material = mat_result.scalars().first()
        if material:
            material.quantity = float(material.quantity or 0) + float(item.quantity)

    await db.delete(issue)
    await db.commit()

    return {"message": "Расход удалён"}