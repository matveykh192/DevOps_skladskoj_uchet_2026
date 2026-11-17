#!/usr/bin/env python3
"""скрипт развертывания и проверки релиза в staging окружении (лр6).

выполняет:
1. блокировку от одновременных деплоев (concurrency lock).
2. загрузку образа из registry без пересборки.
3. запуск контейнеров в изолированном staging окружении.
4. post-deploy проверки: контейнеры, /health, /version, основной пользовательский сценарий.
5. откат (rollback) к предыдущей успешной версии при сбое или по команде.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = ROOT / "deploy"
LOCK_FILE = DEPLOY_DIR / ".deploy.lock"
HISTORY_FILE = DEPLOY_DIR / "releases.log"
LAST_SUCCESS_FILE = DEPLOY_DIR / ".last_successful_release"
COMPOSE_PROJECT = "warehouse-staging"
COMPOSE_FILE = ROOT / "docker-compose.staging.yml"
ENV_FILE = DEPLOY_DIR / ".env.staging"


def compose_base_cmd():
    return ["docker", "compose", "-p", COMPOSE_PROJECT, "-f", str(COMPOSE_FILE)]


class DeployError(Exception):
    pass


def run_cmd(cmd, env=None, check=True, capture=False):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=merged_env,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


class DeployLock:
    # блокировка от параллельных конфликтующих развертываний (пункт 11 лр6)
    def __enter__(self):
        DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
        if LOCK_FILE.exists():
            try:
                pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
                # проверяем жив ли процесс
                import psutil
                if not psutil.pid_exists(pid):
                    LOCK_FILE.unlink(missing_ok=True)
                else:
                    raise DeployError(f"развертывание уже выполняется другим процессом (pid: {pid})")
            except ImportError:
                # без psutil проверяем по времени модификации (старше 5 минут - сбрасываем)
                mtime = LOCK_FILE.stat().st_mtime
                if time.time() - mtime > 300:
                    LOCK_FILE.unlink(missing_ok=True)
                else:
                    raise DeployError("обнаружен активный файл блокировки deploy.lock")
            except ValueError:
                LOCK_FILE.unlink(missing_ok=True)
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if LOCK_FILE.exists():
            LOCK_FILE.unlink(missing_ok=True)


def get_current_release():
    if LAST_SUCCESS_FILE.exists():
        return LAST_SUCCESS_FILE.read_text(encoding="utf-8").strip()
    return None


def record_success(tag, commit_sha):
    LAST_SUCCESS_FILE.write_text(tag, encoding="utf-8")
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] SUCCESS tag={tag} commit={commit_sha}\n")


def record_failure(tag, reason):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] FAILED tag={tag} reason={reason}\n")


def http_get(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "Warehouse-CD-Runner"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")


def wait_for_service(url, expected_code=200, max_attempts=15, delay=2):
    for i in range(max_attempts):
        try:
            status, body = http_get(url)
            if status == expected_code:
                return body
        except Exception:
            pass
        time.sleep(delay)
    raise DeployError(f"сервис по адресу {url} не ответил за {max_attempts * delay} сек")


def check_staging_health(host_port):
    # проверка 1: контейнеры в docker compose ps
    res = run_cmd(compose_base_cmd() + ["ps", "--format", "json"], capture=True)
    if not res.stdout.strip():
        raise DeployError("контейнеры staging не запущены")

    # проверка 2: служебный адрес /health
    health_url = f"http://127.0.0.1:{host_port}/health"
    body = wait_for_service(health_url, expected_code=200)
    data = json.loads(body)
    if data.get("status") != "healthy" or data.get("database") != "connected":
        raise DeployError(f"неуспешный healthcheck: {body}")
    print("  [PASS] служебный адрес /health доступен (статус: healthy, БД подключена)")

    # проверка 3: служебный адрес /version (пункт 8 лр6)
    version_url = f"http://127.0.0.1:{host_port}/version"
    ver_body = wait_for_service(version_url, expected_code=200)
    ver_data = json.loads(ver_body)
    if ver_data.get("status") != "ok":
        raise DeployError(f"неверный ответ /version: {ver_body}")
    print(f"  [PASS] служебный адрес /version подтвержден (версия: {ver_data.get('version')}, коммит: {ver_data.get('commit_sha')})")

    # проверка 4: основной пользовательский сценарий (smoke-тест)
    materials_url = f"http://127.0.0.1:{host_port}/materials/"
    mat_body = wait_for_service(materials_url, expected_code=200)
    mat_data = json.loads(mat_body)
    if not isinstance(mat_data, list):
        raise DeployError("основной сценарий (/materials) вернул некорректный формат данных")
    print(f"  [PASS] основной пользовательский сценарий работает (материалов в базе: {len(mat_data)})")


def deploy(tag, registry_image=None, host_port="8080", simulate_error=None):
    print("=================================================================")
    print(f"  ЗАПУСК РАЗВЕРТЫВАНИЯ РЕЛИЗА: {tag}")
    print("=================================================================")

    current_tag = get_current_release()
    print(f"[*] текущая работающая версия: {current_tag or 'нет (первый релиз)'}")

    # проверка учетной записи/прав (пункт 2)
    deploy_user = os.environ.get("DEPLOY_USER") or os.environ.get("USER") or os.environ.get("USERNAME") or "deploy-bot"
    print(f"[*] учетная запись для деплоя: {deploy_user}")

    # проверка симуляций сбоев для защиты
    if simulate_error == "registry_unreachable":
        print("[!] СИМУЛЯЦИЯ: registry недоступен (ошибка сети/авторизации)")
        raise DeployError("connection to registry failed: authentication required / timeout")

    if simulate_error == "invalid_tag":
        print(f"[!] СИМУЛЯЦИЯ: попытка загрузки несуществующего тега {tag}")
        res = run_cmd(["docker", "pull", f"nonexistent-registry.local/warehouse-app:{tag}"], check=False, capture=True)
        raise DeployError(f"образ с тегом {tag} не найден в registry")

    # подготовка переменных окружения
    env = {
        "IMAGE_TAG": tag,
        "STAGING_PORT": str(host_port),
        "REGISTRY_IMAGE": registry_image or os.environ.get("REGISTRY_IMAGE", "warehouse-app"),
    }

    if simulate_error == "missing_env":
        print("[!] СИМУЛЯЦИЯ: пропущена обязательная переменная окружения WAREHOUSE_DB_PASSWORD")
        env["WAREHOUSE_DB_PASSWORD"] = ""
        env["DATABASE_URL"] = "postgresql+asyncpg://empty_user@invalid_host:5432/bad_db"

    # шаг 1: получение образа из registry без пересборки (пункт 3)
    target_image = f"{env['REGISTRY_IMAGE']}:{tag}"
    print(f"[*] шаг 1: получение образа {target_image} (без пересборки)...")
    # для локального тестирования, если образ уже есть локально, pull может пройти или пропустить
    pull_res = run_cmd(["docker", "image", "inspect", target_image], check=False, capture=True)
    if pull_res.returncode != 0:
        # если нет локально, пробуем стянуть
        print(f"[*] скачиваем образ {target_image} из registry...")
        p = run_cmd(["docker", "pull", target_image], check=False)
        if p.returncode != 0:
            raise DeployError(f"не удалось получить образ {target_image} из registry")
    else:
        print(f"  [OK] проверенный образ {target_image} готов к развертыванию")

    # шаг 2: запуск контейнеров в staging
    print(f"[*] шаг 2: развертывание контейнеров staging на порту {host_port}...")
    up_cmd = compose_base_cmd() + ["up", "-d"]
    up_res = run_cmd(up_cmd, env=env, check=False)
    if up_res.returncode != 0:
        raise DeployError("сбой команды docker compose up")

    # шаг 2.1: накат миграций схемы базы данных в staging
    print("[*] шаг 2.1: применение миграций alembic upgrade head в окружении staging...")
    time.sleep(3)
    mig_res = run_cmd(
        compose_base_cmd() + [
            "exec", "-T",
            "-e", "WAREHOUSE_ALLOW_MIGRATE=YES_I_HAVE_A_BACKUP",
            "staging-app", "alembic", "upgrade", "head"
        ],
        check=False,
        capture=True
    )
    if mig_res.returncode != 0:
        print(f"  [WARN] предупреждение миграций: {mig_res.stderr.strip() or mig_res.stdout.strip()}")

    # шаг 3: пост-проверки релиза (пункт 7 и 8)
    print("[*] шаг 3: выполнение проверок работающего релиза (smoke tests)...")
    try:
        if simulate_error == "broken_health":
            print("[!] СИМУЛЯЦИЯ: приложение запущено, но /health возвращает 503")
            time.sleep(2)
            raise DeployError("неуспешный healthcheck: база данных отключена (503 Service Unavailable)")

        if simulate_error == "broken_scenario":
            print("[!] СИМУЛЯЦИЯ: healthcheck прошел, но основной сценарий (/materials) возвращает 500")
            time.sleep(2)
            raise DeployError("основной пользовательский сценарий упал с ошибкой 500 Internal Server Error")

        check_staging_health(host_port)
    except Exception as e:
        record_failure(tag, str(e))
        print(f"\n[FAIL] релиз {tag} НЕ прошел проверку после развертывания!")
        print(f"       причина: {e}")
        # автоматический откат при падении (пункт 9 и 10)
        if current_tag and current_tag != tag:
            print(f"[*] выполняем автоматический откат к предыдущей рабочей версии: {current_tag}...")
            rollback(current_tag, host_port=host_port)
        raise

    # шаг 4: фиксация успешного релиза
    record_success(tag, os.environ.get("COMMIT_SHA", "local"))
    print("-----------------------------------------------------------------")
    print(f"[SUCCESS] Релиз {tag} успешно развернут и прошел все проверки!")
    print(f"URL окружения: http://127.0.0.1:{host_port}")
    print("-----------------------------------------------------------------")


def rollback(target_tag=None, host_port="8080"):
    print("=================================================================")
    print("  ПРОЦЕДУРА ОТКАТА (ROLLBACK) К ПРЕДЫДУЩЕЙ ВЕРСИИ")
    print("=================================================================")

    if not target_tag:
        target_tag = get_current_release()

    if not target_tag:
        raise DeployError("нет сохраненной информации о предыдущей успешной версии")

    print(f"[*] возвращаем версию: {target_tag}")
    env = {
        "IMAGE_TAG": target_tag,
        "STAGING_PORT": str(host_port),
        "REGISTRY_IMAGE": os.environ.get("REGISTRY_IMAGE", "warehouse-app"),
    }
    run_cmd(compose_base_cmd() + ["up", "-d"], env=env)
    print("[*] проверяем работоспособность восстановленной версии...")
    check_staging_health(host_port)
    record_success(target_tag, "rollback")
    print(f"[SUCCESS] Успешный откат к версии {target_tag}!")


def main():
    parser = argparse.ArgumentParser(description="CD Deploy and Release Verification Script")
    parser.add_argument("--tag", default="latest", help="тег образа для развертывания")
    parser.add_argument("--port", default="8080", help="порт staging на хосте")
    parser.add_argument("--registry-image", default=None, help="имя образа в registry")
    parser.add_argument("--rollback", action="store_true", help="выполнить ручной откат к предыдущей версии")
    parser.add_argument("--check-only", action="store_true", help="только проверить текущее окружение")
    parser.add_argument(
        "--simulate-error",
        choices=["invalid_tag", "missing_env", "broken_health", "broken_scenario", "registry_unreachable"],
        help="симуляция сценариев сбоя для демонстрации преподавателю на защите",
    )

    args = parser.parse_args()

    try:
        with DeployLock():
            if args.check_only:
                check_staging_health(args.port)
            elif args.rollback:
                rollback(host_port=args.port)
            else:
                deploy(
                    tag=args.tag,
                    registry_image=args.registry_image,
                    host_port=args.port,
                    simulate_error=args.simulate_error,
                )
    except DeployError as err:
        print(f"\n[ERROR] Ошибка развертывания: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"\n[UNEXPECTED ERROR] {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
