"""Isolated PostgreSQL backup and recovery verification.

Only accesses warehouse_backup_demo/warehouse_backup_verify on isolated
warehouse-lr3-test/test-db. Never accepts a DB URL or arbitrary DB name.
Run on host (Python 3.8+, Docker Desktop). pg_dump/pg_restore run in test-db.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

COMPOSE = ["docker", "compose", "-p", "warehouse-lr3-test", "-f", "docker-compose.test.yml"]
DB_USER = "warehouse_test_user"
DB_HOST = "test-db"
DB_PASS = "test_only_not_for_production"
DBS = {"demo": "warehouse_backup_demo", "check": "warehouse_backup_verify"}
ROOT = Path(__file__).resolve().parent.parent
BACKUPS = ROOT / "backups"


def run(args, *, input_file=None, output_file=None):
    """Run external commands; errors always terminate the process."""
    stdin = input_file if input_file is not None else None
    stdout = output_file if output_file is not None else None
    subprocess.run(args, stdin=stdin, stdout=stdout, check=True, cwd=ROOT)


def pg(*args):
    return COMPOSE + ["exec", "-T", "test-db", *args]


def sql(db, statement):
    run(pg("psql", "-v", "ON_ERROR_STOP=1", "-U", DB_USER, "-d", db, "-c", statement))


def query(db, statement):
    proc = subprocess.run(
        pg("psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", DB_USER, "-d", db, "-c", statement),
        stdout=subprocess.PIPE, check=True, cwd=ROOT, text=True
    )
    return proc.stdout.strip()


def ensure_stack():
    # Explicitly only the named isolated test stack; never `docker compose` default.
    run(COMPOSE + ["up", "-d", "--wait", "test-db"])
    # Verify the service environment before any database action (fail closed).
    actual = subprocess.run(
        pg("printenv", "POSTGRES_DB", "POSTGRES_USER"),
        stdout=subprocess.PIPE, check=True, cwd=ROOT, text=True
    ).stdout.splitlines()
    if actual != ["warehouse_test_db", DB_USER]:
        raise RuntimeError("Unexpected PostgreSQL instance; refusing backup/restore")


def fresh_demo(db):
    # Destructive ONLY for the two hard-coded, disposable databases above.
    sql("postgres", f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
    sql("postgres", f'CREATE DATABASE "{db}"')
    url = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{db}"
    run(COMPOSE + ["run", "--rm", "--build", "-e", f"DATABASE_URL={url}", "test-runner", "python", "-m", "alembic", "upgrade", "head"])
    sql(db, "INSERT INTO measurement_units (name, short_name) VALUES ('pieces', 'pcs')")
    sql(db, "INSERT INTO materials (name, measurement_unit_id, quantity, minimum_stock) "
            "VALUES ('Backup check material', (SELECT id FROM measurement_units WHERE short_name='pcs'), 12.500, 5.000)")
    print(f"PREPARED: disposable {db} with 3 Alembic revisions and stock 12.500")


def archive_path(kind):
    BACKUPS.mkdir(parents=True, exist_ok=True)
    return BACKUPS / f"{DBS[kind]}.dump"


def backup(db, archive):
    with archive.open("wb") as stream:
        run(pg("pg_dump", "-U", DB_USER, "-d", db, "-Fc", "--no-owner", "--no-acl"), output_file=stream)
    with archive.open("rb") as stream:
        signature = stream.read(5)
    if archive.stat().st_size < 100 or signature != b"PGDMP":
        raise RuntimeError("Invalid or empty PostgreSQL custom-format archive")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    print(f"BACKUP OK: {archive} ({archive.stat().st_size} bytes; sha256={sha})")


def restore(db, archive):
    if not archive.is_file():
        raise RuntimeError("Missing archive; refusing restore")
    with archive.open("rb") as stream:
        signature = stream.read(5)
    if signature != b"PGDMP":
        raise RuntimeError("Missing or invalid archive; refusing restore")
    # Never restore into warehouse_test_db or the original warehouse_db.
    if db not in DBS.values():
        raise RuntimeError("Refusing non-disposable restore target")
    with archive.open("rb") as stream:
        run(pg("pg_restore", "-U", DB_USER, "-d", db,
                   "--clean", "--if-exists", "--no-owner", "--no-acl", "--exit-on-error"), input_file=stream)
    print(f"RESTORE OK: {db} from {archive.name}")


def snapshot(db):
    return query(db, "SELECT name || ':' || quantity::text || ':' || minimum_stock::text FROM materials ORDER BY id")


def check():
    db = DBS["check"]
    fresh_demo(db)
    before = snapshot(db)
    if before != "Backup check material:12.500:5.000":
        raise AssertionError(f"Unexpected seed: {before!r}")
    archive = archive_path("check")
    backup(db, archive)
    # Intentional destruction only in disposable *verify* DB.
    sql(db, "DELETE FROM materials")
    if snapshot(db):
        raise AssertionError("Corruption demonstration did not remove material")
    print("CORRUPTION CONFIRMED: material deliberately deleted in disposable verify DB")
    restore(db, archive)
    after = snapshot(db)
    if after != before:
        raise AssertionError(f"Recovery mismatch: before={before!r}; after={after!r}")
    if query(db, "SELECT version_num FROM alembic_version") != "003_minimum_stock":
        raise AssertionError("Alembic version not restored")
    print("PASS: stock restored exactly (12.500) and Alembic revision 003 preserved")
    print("BACKUP/RESTORE CHECKS PASSED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore", "check"))
    args = parser.parse_args()
    ensure_stack()
    if args.action == "check":
        check()
    elif args.action == "backup":
        db = DBS["demo"]
        fresh_demo(db)
        backup(db, archive_path("demo"))
    else:
        db = DBS["demo"]
        # Caller controls only demo DB. No auto-creation or drop on restore.
        restore(db, archive_path("demo"))
        print(f"Material after restore: {snapshot(db)}")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, RuntimeError, AssertionError, OSError) as exc:
        print(f"BACKUP/RESTORE FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
