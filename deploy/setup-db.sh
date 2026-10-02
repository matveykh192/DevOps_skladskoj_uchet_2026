#!/usr/bin/env bash
#
# Настройка db-сервера: PostgreSQL + БД + пользователь + firewall.
# Запускать на db-сервере от root (sudo bash setup-db.sh).
#
set -euo pipefail

# ---- Параметры ----
APP_IP="${APP_IP:-192.168.56.10}"
DB_IP="${DB_IP:-192.168.56.20}"
DB_NAME="${DB_NAME:-warehouse_db}"
DB_USER="${DB_USER:-warehouse_user}"
DB_PASSWORD="${DB_PASSWORD:-}"
SCHEMA_FILE="${SCHEMA_FILE:-/opt/warehouse-deploy/init-standalone.sql}"

if [[ -z "$DB_PASSWORD" ]]; then
    echo "ОШИБКА: не задан DB_PASSWORD" >&2
    echo "Запустите: sudo DB_PASSWORD='...' bash $0" >&2
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "ОШИБКА: скрипт нужно запускать от root (sudo)" >&2
    exit 1
fi

echo "===> [1/6] Установка PostgreSQL и ufw"
apt update
DEBIAN_FRONTEND=noninteractive apt install -y postgresql postgresql-contrib ufw

PG_VERSION=$(ls /etc/postgresql/ | head -1)
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

echo "===> [2/6] Настройка listen_addresses"
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "$PG_CONF"

echo "===> [3/6] Настройка pg_hba.conf"
# Удаляем прежние правила (если перезапускаем скрипт)
sed -i "/# warehouse-app/d" "$PG_HBA"

# Вставляем перед первой строкой host all all
{
    echo "# warehouse-app: разрешить подключения с app-сервера"
    echo "host    ${DB_NAME}    ${DB_USER}    ${APP_IP}/32    scram-sha-256"
} | cat - "$PG_HBA" > /tmp/pg_hba.new
mv /tmp/pg_hba.new "$PG_HBA"

systemctl restart postgresql
systemctl enable postgresql

echo "===> [4/6] Создание БД и пользователя"
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
    ELSE
        ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
    END IF;
END
\$\$;

SELECT 'CREATE DATABASE ${DB_NAME} OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL

sudo -u postgres psql -d "$DB_NAME" <<SQL
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${DB_USER};
GRANT USAGE ON SCHEMA public TO ${DB_USER};
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE ${DB_NAME} FROM PUBLIC;
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

echo "===> [5/6] Заливка схемы"
if [[ -f "$SCHEMA_FILE" ]]; then
    sudo -u postgres psql -d "$DB_NAME" -f "$SCHEMA_FILE"
else
    echo "ПРЕДУПРЕЖДЕНИЕ: файл $SCHEMA_FILE не найден, пропускаем заливку схемы"
    echo "Скопируйте init-standalone.sql в $SCHEMA_FILE и выполните заново"
fi

echo "===> [6/6] Настройка firewall (ufw)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow from "${APP_IP}" to any port 5432 proto tcp comment 'PostgreSQL from app-server'
ufw --force enable
ufw status verbose

echo
echo "===> Готово. db-сервер настроен."
echo "    БД:        ${DB_NAME}"
echo "    Пользователь: ${DB_USER}"
echo "    Доступ:    только с ${APP_IP}"