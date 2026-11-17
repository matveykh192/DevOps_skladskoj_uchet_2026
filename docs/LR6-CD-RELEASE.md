# Лабораторная работа №6: Continuous Delivery и проверка работающего релиза

## 1. Концепция релиза (Результат работы)
> **«Успешная сборка не равна успешному релизу: версия принимается только после проверки в целевой среде».**

Пайплайн Continuous Delivery (CD) гарантирует, что образ приложения развертывается в предэксплуатационном окружении (staging) без пересборки, проходит автоматические проверки (`/health`, `/version`, основной пользовательский сценарий) и только при 100% успехе объявляется стабильным релизом. В случае любого сбоя выполняется автоматический или ручной откат (rollback) к предыдущей проверенной версии.

---

## 2. Архитектура решения и окружение

```
┌────────────────────────────────────────────────────────┐
│  CI/CD Pipeline (GitHub Actions)                       │
│  [build & publish] ──> [ghcr.io (Container Registry)]  │
└───────────────────────────────────┬────────────────────┘
                                    │ pull image (без пересборки)
                                    ▼
┌────────────────────────────────────────────────────────┐
│  Предэксплуатационное окружение (Staging)              │
│  docker-compose.staging.yml                            │
│                                                        │
│  [ Клиент / Smoke-тесты ] ──> HTTP :8080               │
│                                    │                   │
│         ┌──────────────────────────▼───────────────┐   │
│         │ Staging Nginx Proxy (:8080 -> :80)       │   │
│         └──────────────────────────┬───────────────┘   │
│                                    │                   │
│         ┌──────────────────────────▼───────────────┐   │
│         │ Staging App (FastAPI, image: registry)   │   │
│         │ non-root, env из .env.staging             │   │
│         └──────────────────────────┬───────────────┘   │
│                                    │                   │
│         ┌──────────────────────────▼───────────────┐   │
│         │ Staging DB (PostgreSQL 15, isolated)     │   │
│         │ volume: warehouse_staging_data           │   │
│         └──────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

---

## 3. Выполнение требований лабораторной работы

| № | Требование | Реализация в проекте | Файлы / Строки |
|---|---|---|---|
| 1 | **Отдельное окружение** | Изолированный стек `docker-compose.staging.yml`, порт `8080`, сеть `warehouse_staging_net`, том `warehouse_staging_data`. | `docker-compose.staging.yml` |
| 2 | **Доступ через отдельную учетную запись** | В скрипте `scripts/deploy.py` и GitHub Actions используется сервисный пользователь `DEPLOY_USER` (`github-actions-cd`). | `scripts/deploy.py`, `.github/workflows/ci.yml` |
| 3 | **Образ из registry без пересборки** | В `docker-compose.staging.yml` отсутствует секция `build:`. Образ забирается командой `docker pull` из `ghcr.io` (или локального registry). | `docker-compose.staging.yml:28` |
| 4 | **Настройки отдельно от образа** | Параметры передаются через файл `deploy/.env.staging` (шаблон `deploy/.env.staging.example`), исключенный из git и docker-образа. | `deploy/.env.staging.example` |
| 5 | **Автоматическое развертывание** | В CI джоба `deploy-staging` запускается автоматически после успеха `publish` (`needs: [publish]`). | `.github/workflows/ci.yml:205` |
| 6 | **Ограничение веткой или ручным подтверждением** | Авто-деплой разрешен только из ветки `main` (`github.ref == 'refs/heads/main'`), либо вручную через `workflow_dispatch`. | `.github/workflows/ci.yml:209` |
| 7 | **Проверка после развертывания** | Проверка `docker compose ps`, `/health` (БД подключена), `/version` (соответствие тега), `/materials/` (пользовательский сценарий). | `scripts/deploy.py:108-142` |
| 8 | **Эндпоинт `/version`** | В `app/main.py` добавлен маршрут `GET /version`, возвращающий `version`, `commit_sha`, `environment`, `instance`. | `app/main.py:121-133` |
| 9 | **Провал релиза при ошибке проверки** | Если smoke-тесты падают, релиз помечается как `FAILED`, выход с кодом `1`, пайплайн горит красным. | `scripts/deploy.py:228-237` |
| 10 | **Развертывание тега и ручной откат** | Запуск `python scripts/deploy.py --tag <tag>` и откат `python scripts/deploy.py --rollback` (цель `make rollback`). | `scripts/deploy.py:246-261` |
| 11 | **Ограничение одновременных деплоев** | Файловая блокировка `DeployLock` (`deploy/.deploy.lock`) и `concurrency: group: staging-release` в GitHub Actions. | `scripts/deploy.py:55-83`, `.github/workflows/ci.yml:210` |
| 12 | **Сквозной выпуск функции** | Ветка `feature/lab6-cd-pipeline`, реализация эндпоинта `/version`, тесты в `tests/test_smoke.py`, запуск `make verify`, релиз `v1.0.0` -> `v1.1.0`. | git history, `tests/test_smoke.py` |
| 13 | **Моделирование неудачного выпуска** | Симуляция падения healthcheck/сценария -> автоматическая фиксация сбоя в `deploy/releases.log` и откат к стабильной версии. | `scripts/deploy.py:180-235` |

---

## 4. Сценарии проверки на защите

### 1) Неверный тег
```bash
python scripts/deploy.py --tag bad-tag-999 --simulate-error invalid_tag
```
*Результат*: Скрипт падает с ошибкой: `образ с тегом bad-tag-999 не найден в registry`. Контейнеры с предыдущей версией не затрагиваются.

### 2) Отсутствующая переменная окружения
```bash
python scripts/deploy.py --tag v1.0.0 --simulate-error missing_env
```
*Результат*: Развертывание прерывается, healthcheck не проходит, релиз бракуется.

### 3) Неуспешный healthcheck
```bash
python scripts/deploy.py --tag v1.1.0 --simulate-error broken_health
```
*Результат*: Контейнер запущен, но `/health` вернул 503. Скрипт фиксирует `[FAIL]` и не считает релиз успешным.

### 4) Приложение запускается, но основной сценарий не работает
```bash
python scripts/deploy.py --tag v1.1.0 --simulate-error broken_scenario
```
*Результат*: `/health` вернул 200, но бизнес-маршрут `/materials` вернул ошибку 500. Релиз отклонен.

### 5) Недоступный registry
```bash
python scripts/deploy.py --tag v1.0.0 --simulate-error registry_unreachable
```
*Результат*: Ошибка подключения к registry блокирует начало деплоя.

### 6) Возврат предыдущей версии (Rollback)
```bash
make rollback
```
*Результат*: В одну команду восстанавливается предыдущая зафиксированная стабильная версия из файла `deploy/.last_successful_release`.
