import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from pathlib import Path

from app.config import settings
from app.database import engine
from app.routers import materials, suppliers, auth, receipts, issues, frontend

# ==========================================
# Логирование
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("warehouse")

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="Складской учёт",
    description="API для управления складом",
    version="0.1.0"
)

# ==========================================
# Раздача статики
# ==========================================
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend" / "static"), name="static")

# ==========================================
# Роутеры
# ==========================================
app.include_router(auth.router)
app.include_router(materials.router)
app.include_router(suppliers.router)
app.include_router(receipts.router)
app.include_router(issues.router)
app.include_router(frontend.router)

# ==========================================
# Кастомные обработчики ошибок
# ==========================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Обработка ошибок валидации (422) — собираем все поля в одно сообщение."""
    errors = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []))
        msg = err.get("msg", "некорректное значение")
        errors.append(f"{loc}: {msg}")

    detail = "Ошибка валидации данных: " + "; ".join(errors) if errors else "Ошибка валидации данных"
    logger.warning("[422] %s %s — %s", request.method, request.url.path, detail)

    return JSONResponse(
        status_code=422,
        content={"detail": detail, "errors": exc.errors()}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Единый формат для HTTPException (400/401/404/...)."""
    logger.info("[%s] %s %s — %s", exc.status_code, request.method, request.url.path, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Ловим всё, что не поймали — 500 с понятным сообщением."""
    logger.exception("[500] %s %s — необработанная ошибка: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"}
    )

# ==========================================
# OpenAPI (кнопка Authorize в Swagger)
# ==========================================

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {
            "type": "oauth2",
            "flows": {"password": {"tokenUrl": "/auth/login", "scopes": {}}}
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# ==========================================
# Health-check
# ==========================================

@app.get("/health", tags=["System"])
async def health_check():
    """
    Служебный адрес проверки работоспособности.
    Проверяет и само приложение, и подключение к БД.
    """
    db_status = "unknown"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error("Health-check: БД недоступна — %s", e)
        db_status = "disconnected"

    ok = db_status == "connected"

    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "healthy" if ok else "unhealthy",
            "database": db_status,
            "version": app.version
        }
    )


# ==========================================
# Startup: вывести подхваченные настройки (без секретов)
# ==========================================
@app.on_event("startup")
async def startup_event():
    logger.info("=== Приложение запускается ===")
    logger.info("Версия: %s", app.version)
    logger.info("DB host: %s", settings.DB_HOST)
    logger.info("DB name: %s", settings.DB_NAME)
    logger.info("SECRET_KEY настроен: %s", bool(settings.SECRET_KEY))