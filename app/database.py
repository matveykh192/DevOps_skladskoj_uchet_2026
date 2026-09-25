from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Создаем асинхронный движок
engine = create_async_engine(settings.DATABASE_URL, echo=False)

# Фабрика сессий
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Базовый класс для всех ORM-моделей
Base = declarative_base()

# Зависимость для получения сессии БД в роутерах
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session