#!/usr/bin/env bash
#
# Обновление приложения на app-сервере.
# Запускать на app-сервере от root (sudo bash deploy.sh).
#
set -euo pipefail

APP_DIR="/opt/warehouse-app"
VENV_DIR="${APP_DIR}/venv"

if [[ $EUID -ne 0 ]]; then
    echo "ОШИБКА: скрипт нужно запускать от root (sudo)" >&2
    exit 1
fi

echo "===> [1/4] Обновление кода из git"
git -C "$APP_DIR" fetch --all
git -C "$APP_DIR" reset --hard origin/main
chown -R warehouse:warehouse "$APP_DIR"

echo "===> [2/4] Обновление зависимостей"
sudo -u warehouse "$VENV_DIR/bin/pip" install --upgrade pip
sudo -u warehouse "$VENV_DIR/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "===> [3/4] Перезапуск службы"
systemctl restart warehouse-app

echo "===> [4/4] Проверка"
sleep 3
systemctl status warehouse-app --no-pager | head -5
echo
curl -s http://127.0.0.1:8000/health || echo "(приложение ещё запускается)"