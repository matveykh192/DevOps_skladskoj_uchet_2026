.PHONY: help setup up down run test quality migrate verify container-check

help:
	@echo Доступные команды:
	@echo   make setup     - Первоначальная настройка проекта
	@echo   make up        - Запуск контейнерного окружения
	@echo   make down      - Остановка контейнерного окружения
	@echo   make run       - Локальный запуск приложения (без Docker)
	@echo   make test      - Автоматические тесты
	@echo   make quality   - Форматирование и статический анализ кода
	@echo   make migrate   - Применение миграций базы данных
	@echo   make verify    - Полный набор локальных проверок
	@echo   make container-check - Проверка работоспособности контейнеров

setup:
	@if not exist .env copy .env.example .env
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	docker compose exec app pytest

quality:
	docker compose exec app ruff check .
	docker compose exec app ruff format .

migrate:
	docker compose exec app alembic upgrade head

verify:
	$(MAKE) quality
	$(MAKE) test

container-check:
	docker compose ps
	@curl -f http://localhost:8000/health || exit 1