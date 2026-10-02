#!/usr/bin/env bash
#
# Настройка app-сервера: Python 3.11, клонирование репозитория, venv,
# systemd-служба, firewall.
# Запускать на app-сервере от root (sudo bash setup-app.sh).
#
set -euo pipefail

# ---- Параметры ----
APP_IP="${APP_IP:-192.168.56.10}"
DB_IP="${DB_IP:-192.168.56.20}"
DB_NAME="${DB_NAME:-warehouse_db}"
DB_USER="${DB_USER:-warehouse_user}"
DB_PASSWORD="${DB_PASSWORD:-}"
APP_SECRET_KEY="${APP_SECRET_KEY:-$(openssl rand -base64 48)}"
APP_REPO="${APP_REPO:-https://github.com/matveykh192/DevOps_skladskoj_uchet_2026.git}"
APP_DIR="/opt/warehouse-app"
ENV_DIR="/etc/warehouse-app"
VENV_DIR="${APP_DIR}/venv"
PYTHON_DIR="/opt/python"
UV_BIN="/usr/local/bin/uv"

if [[ -z "$DB_PASSWORD" ]]; then
    echo "ОШИБКА: не задан DB_PASSWORD" >&2
    echo "Запустите: sudo DB_PASSWORD='...' bash $0" >&2
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "ОШИБКА: скрипт нужно запускать от root (sudo)" >&2
    exit 1
fi

echo "===> [1/8] Установка базовых пакетов"
apt update
DEBIAN_FRONTEND=noninteractive apt install -y \
    git curl ca-certificates ufw build-essential

echo "===> [2/8] Установка uv и Python 3.11"
if [[ ! -x "$UV_BIN" ]]; then
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh
fi

uv python install 3.11

# Копируем Python в /opt, чтобы был доступен пользователю warehouse
mkdir -p "$PYTHON_DIR"
PY_SRC=$(uv python find 3.11)
PY_PREFIX=$(dirname "$(dirname "$PY_SRC")")
PY_DEST="${PYTHON_DIR}/$(basename "$PY_PREFIX")"

if [[ ! -d "$PY_DEST" ]]; then
    cp -rL "$PY_PREFIX" "$PY_DEST"
fi
chmod -R o+rX "$PYTHON_DIR"
PY311="${PY_DEST}/bin/python3.11"

echo "===> [3/8] Создание системного пользователя warehouse"
if ! id warehouse &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d "$APP_DIR" warehouse
fi

echo "===> [4/8] Создание каталогов"
mkdir -p "$APP_DIR" "$ENV_DIR" /var/log/warehouse-app
chown warehouse:warehouse "$APP_DIR"
chmod 755 "$APP_DIR"
chown root:warehouse "$ENV_DIR"
chmod 750 "$ENV_DIR"
chown warehouse:warehouse /var/log/warehouse-app
chmod 750 /var/log/warehouse-app

echo "===> [5/8] Клонирование репозитория"
if [[ -d "${APP_DIR}/.git" ]]; then
    git -C "$APP_DIR" pull
else
    rm -rf "${APP_DIR:?}/"*
    git clone "$APP_REPO" /tmp/warehouse-src
    cp -r /tmp/warehouse-src/* "$APP_DIR/"
    chown -R warehouse:warehouse "$APP_DIR"
fi

echo "===> [6/8] Создание venv и установка зависимостей"
rm -rf "$VENV_DIR"
sudo -u warehouse "$PY311" -m venv "$VENV_DIR"
sudo -u warehouse "$VENV_DIR/bin/pip" install --upgrade pip
sudo -u warehouse "$VENV_DIR/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "===> [7/8] Создание конфигурации"
cat > "${ENV_DIR}/warehouse.env" <<ENV
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_IP}:5432/${DB_NAME}
SECRET_KEY=${APP_SECRET_KEY}
APP_HOST=0.0.0.0
APP_PORT=8000
ENV
chown root:warehouse "${ENV_DIR}/warehouse.env"
chmod 640 "${ENV_DIR}/warehouse.env"

echo "===> [8/8] Установка systemd-службы"
cat > /etc/systemd/system/warehouse-app.service <<'UNIT'
[Unit]
Description=Warehouse Accounting API (FastAPI + Uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=warehouse
Group=warehouse
WorkingDirectory=/opt/warehouse-app
EnvironmentFile=/etc/warehouse-app/warehouse.env
ExecStart=/opt/warehouse-app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=warehouse-app

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/var/log/warehouse-app

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable warehouse-app
systemctl restart warehouse-app

echo "===> Настройка firewall"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 8000/tcp comment 'Warehouse API'
ufw --force enable
ufw status verbose

echo
echo "===> Готово. app-сервер настроен."
echo "    Статус: systemctl status warehouse-app"
echo "    Логи:   journalctl -u warehouse-app -f"
echo "    Health: curl http://127.0.0.1:8000/health"