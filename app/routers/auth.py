from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from app.auth import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # ищем юзера по логину
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()

    # проверяем пароль и активность
    if not user or not verify_password(form_data.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=401, detail="неверный логин или пароль")

    # создаем токен
    access_token = create_access_token(data={"sub": user.username})
    
    return {"access_token": access_token, "token_type": "bearer"}