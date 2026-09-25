from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(tags=["Frontend"])

# Определяем корневую папку проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "frontend" / "templates")

# Главная страница
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("base.html", {"request": request})

# Страница входа (работает и по /login, и по /login.html)
@router.get("/login", response_class=HTMLResponse)
@router.get("/login.html", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Страница материалов
@router.get("/materials", response_class=HTMLResponse)
@router.get("/materials.html", response_class=HTMLResponse)
async def materials_page(request: Request):
    return templates.TemplateResponse("materials.html", {"request": request})

# Страница поступлений
@router.get("/receipts", response_class=HTMLResponse)
@router.get("/receipts.html", response_class=HTMLResponse)
async def receipts_page(request: Request):
    return templates.TemplateResponse("receipts.html", {"request": request})

# Страница расхода
@router.get("/issues", response_class=HTMLResponse)
@router.get("/issues.html", response_class=HTMLResponse)
async def issues_page(request: Request):
    return templates.TemplateResponse("issues.html", {"request": request})