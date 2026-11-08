#!/usr/bin/env python3
"""Restore database backup into a brand-new Docker volume (Defense Requirement).

Usage:
    python scripts/restore_new_volume.py [--archive backups/warehouse_db.dump] [--volume-name postgres_data_restored]

Flow:
1. Validates PostgreSQL custom dump archive.
2. Creates a new isolated Docker volume (e.g. 'warehouse_postgres_data_restored').
3. Starts a temporary PostgreSQL container attached exclusively to the new volume.
4. Waits for PostgreSQL initial two-phase initialization to fully complete.
5. Restores the database from the backup archive.
6. Verifies data integrity (tables, records, migration version) in the new volume.
7. Cleans up the temporary container, leaving the new volume verified and ready.
"""

import argparse
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE = ROOT / "backups" / "warehouse_db.dump"
DEFAULT_VOLUME = "warehouse_postgres_data_restored"
PG_IMAGE = "postgres:15-alpine"
DB_USER = "warehouse_user"
DB_NAME = "warehouse_db"
DB_PASS = "secure_password_123"


def run(cmd, *, capture=False, check=True):
    return subprocess.run(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
        check=check,
    )


def restore_into_new_volume(archive_path: Path, volume_name: str):
    if not archive_path.is_file():
        raise RuntimeError(f"Backup archive not found: {archive_path}")

    print(f"[*] Step 1: Validating archive: {archive_path.name} ({archive_path.stat().st_size} bytes)")
    with archive_path.open("rb") as f:
        header = f.read(5)
        if header != b"PGDMP":
            raise RuntimeError(f"File {archive_path} is not a valid PostgreSQL custom-format archive")

    print(f"[*] Step 2: Creating new Docker volume '{volume_name}'...")
    # Remove old restored volume if exists
    run(["docker", "volume", "rm", "-f", volume_name], check=False)
    run(["docker", "volume", "create", volume_name])

    temp_container = f"warehouse_restore_runner_{uuid.uuid4().hex[:8]}"
    print(f"[*] Step 3: Starting temporary container '{temp_container}' with new volume...")
    run([
        "docker", "run", "-d",
        "--name", temp_container,
        "-e", f"POSTGRES_USER={DB_USER}",
        "-e", f"POSTGRES_PASSWORD={DB_PASS}",
        "-e", f"POSTGRES_DB={DB_NAME}",
        "-v", f"{volume_name}:/var/lib/postgresql/data",
        PG_IMAGE
    ])

    try:
        # Wait for PostgreSQL to complete initial setup and stabilize
        print("[*] Waiting for PostgreSQL in new volume to complete initialization...")
        ready = False
        consecutive_success = 0
        for _ in range(45):
            res = run([
                "docker", "exec", temp_container,
                "psql", "-h", "127.0.0.1", "-U", DB_USER, "-d", DB_NAME, "-c", "SELECT 1"
            ], capture=True, check=False)
            if res.returncode == 0:
                consecutive_success += 1
                if consecutive_success >= 3:
                    ready = True
                    break
            else:
                consecutive_success = 0
            time.sleep(1)

        if not ready:
            raise RuntimeError("PostgreSQL in restore container failed to stabilize in time")

        print("[*] Step 4: Copying backup dump into container and executing pg_restore...")
        container_dump = f"/tmp/{archive_path.name}"
        run(["docker", "cp", str(archive_path), f"{temp_container}:{container_dump}"])

        # pg_restore into database using explicit host 127.0.0.1
        run([
            "docker", "exec", temp_container,
            "pg_restore", "-h", "127.0.0.1", "-U", DB_USER, "-d", DB_NAME,
            "--no-owner", "--no-acl", container_dump
        ])

        print("[*] Step 5: Verifying restored database integrity...")
        # Check alembic revision
        ver = run([
            "docker", "exec", temp_container,
            "psql", "-X", "-At", "-h", "127.0.0.1", "-U", DB_USER, "-d", DB_NAME,
            "-c", "SELECT version_num FROM alembic_version;"
        ], capture=True).stdout.strip()

        # Check table count
        tables_count = run([
            "docker", "exec", temp_container,
            "psql", "-X", "-At", "-h", "127.0.0.1", "-U", DB_USER, "-d", DB_NAME,
            "-c", "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
        ], capture=True).stdout.strip()

        # Check materials count
        mat_count = run([
            "docker", "exec", temp_container,
            "psql", "-X", "-At", "-h", "127.0.0.1", "-U", DB_USER, "-d", DB_NAME,
            "-c", "SELECT count(*) FROM materials;"
        ], capture=True).stdout.strip()

        print("-----------------------------------------------------------------")
        print(f"  [RESTORE VERIFIED IN NEW VOLUME: '{volume_name}']")
        print(f"  -> Alembic migration head: {ver}")
        print(f"  -> Public tables count:    {tables_count}")
        print(f"  -> Materials records count:{mat_count}")
        print("-----------------------------------------------------------------")
        print(f"[SUCCESS] Database successfully restored into new volume '{volume_name}'.")

    finally:
        print(f"[*] Step 6: Cleaning up temporary container '{temp_container}'...")
        run(["docker", "rm", "-f", temp_container], check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE, help="Path to dump archive")
    parser.add_argument("--volume-name", default=DEFAULT_VOLUME, help="Name of new Docker volume")
    args = parser.parse_args()

    try:
        restore_into_new_volume(args.archive.resolve(), args.volume_name)
    except Exception as exc:
        print(f"[ERROR] Restore to new volume failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
