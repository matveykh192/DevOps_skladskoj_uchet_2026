# Project verification workflow. GNU Make on Windows/Linux.
COMPOSE = docker compose
TEST_COMPOSE = $(COMPOSE) -p warehouse-lr3-test -f docker-compose.test.yml
.PHONY: help setup up down run test test-unit test-integration quality sast verify migrate backup restore restore-main backup-demo restore-demo backup-check test-clean container-check migration-check restore-new-volume

help:
	@echo "setup up down run test test-unit test-integration quality sast verify migrate backup restore restore-main backup-demo restore-demo backup-check test-clean container-check restore-new-volume"

# Initial setup builds images only. It never changes a production DB.
setup:
	$(COMPOSE) build
	$(TEST_COMPOSE) build

# Environment modifications strictly guarded by container-check gate
up: container-check
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

run: container-check
	$(COMPOSE) up -d

test:
	$(TEST_COMPOSE) run --build --rm test-runner

test-unit:
	$(TEST_COMPOSE) run --build --rm --no-deps test-runner pytest -q -m unit tests

test-integration:
	$(TEST_COMPOSE) run --build --rm test-runner pytest -q -m integration tests

quality:
	$(TEST_COMPOSE) run --build --rm --no-deps test-runner ruff check app tests
	$(TEST_COMPOSE) run --rm --no-deps test-runner ruff format --check app tests

sast:
	$(TEST_COMPOSE) run --build --rm --no-deps test-runner bandit -r app -ll

# Mandatory gate: container environment policy, quality, SAST, unit/integration tests, migrations and backup checks.
verify: container-check quality sast test migration-check backup-check

# Automated container environment compliance gate (Lab 4 requirement 12, 13)
container-check:
	python scripts/container_check.py

# Isolated checks use separate temporary databases, never the main DB.
migration-check:
	$(TEST_COMPOSE) run --build --rm test-runner python scripts/check_migrations.py

# A real database schema must be audited and backed up before migration.
migrate:
	@echo "Use make migration-check for isolated verification. Real DB migration requires separate schema audit and backup."
	@exit 1

# Backup the actual application database (never recreates it).
backup:
	python scripts/app_backup.py backup

# Non-destructive recovery proof, restoring into warehouse_restore_verify.
restore:
	python scripts/app_backup.py restore-check

# Defense requirement: restore database into a brand-new Docker volume.
restore-new-volume:
	python scripts/restore_new_volume.py

# DANGEROUS: requires RESTORE_CONFIRM=RESTORE_WAREHOUSE_DB and stops the app.
restore-main:
	python scripts/app_backup.py restore-main --confirm "$(RESTORE_CONFIRM)"

# Original isolated demonstration targets remain available.
backup-demo:
	python scripts/backup_restore.py backup

restore-demo:
	python scripts/backup_restore.py restore

backup-check:
	python scripts/backup_restore.py check

test-clean:
	$(TEST_COMPOSE) down -v --remove-orphans
