from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Основное подключение к БД
    DATABASE_URL: str = "postgresql+asyncpg://warehouse_user:secure_password_123@db:5432/warehouse_db"

    # Отдельные поля, чтобы показывать в логах без пароля
    DB_HOST: str = "db"
    DB_NAME: str = "warehouse_db"

    # безопасность
    SECRET_KEY: str = "change_me_in_production"

    # параметры окружения и версии (для лр6)
    APP_ENV: str = "production"
    APP_VERSION: str = "0.1.0"
    COMMIT_SHA: str = "unknown"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
