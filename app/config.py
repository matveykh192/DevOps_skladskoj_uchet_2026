from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Основное подключение к БД
    DATABASE_URL: str = "postgresql+asyncpg://warehouse_user:secure_password_123@db:5432/warehouse_db"

    # Отдельные поля, чтобы показывать в логах без пароля
    DB_HOST: str = "db"
    DB_NAME: str = "warehouse_db"

    # Безопасность
    SECRET_KEY: str = "change_me_in_production"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()