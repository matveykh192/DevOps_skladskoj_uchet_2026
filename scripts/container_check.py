#!/usr/bin/env python3
"""Automated verification of container environment compliance (Lab 4).

Zero third-party dependencies (uses Python standard library only).

Enforces mandatory operational requirements:
1. Tag policy: Prohibition of ':latest' and untagged base images in Dockerfile and Compose.
2. User policy: Prohibition of running containers as root (UID != 0).
3. Secret policy: Prohibition of embedding hardcoded secrets into Dockerfiles/images.
4. Healthcheck policy: Active healthchecks mandatory for all services.
5. Port security policy: DB port isolated; App direct access forbidden (proxied via Nginx).
6. Resource policy: Explicit CPU and memory limits defined on all services.
7. Graceful shutdown policy: STOPSIGNAL and exec CMD configured.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class VerificationFailure(Exception):
    pass


def log_step(name: str, passed: bool, details: str = ""):
    status = "\033[92m[PASS]\033[0m" if passed else "\033[91m[FAIL]\033[0m"
    if not sys.stdout.isatty():
        status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {name}")
    if details:
        print(f"         -> {details}")


def get_compose_config(file_name="docker-compose.yml"):
    comp_file = ROOT / file_name
    if not comp_file.is_file():
        raise VerificationFailure(f"Compose configuration file missing: {file_name}")

    cmd = ["docker", "compose", "-f", str(comp_file), "config", "--format", "json"]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, cwd=ROOT, text=True)
        return json.loads(proc.stdout)
    except subprocess.CalledProcessError as e:
        raise VerificationFailure(f"docker compose config failed: {e.stderr.strip()}")
    except json.JSONDecodeError as e:
        raise VerificationFailure(f"Failed to parse compose json output: {e}")


def check_no_latest():
    """Rule 1: Forbid ':latest' and untagged base images in Dockerfiles and Compose."""
    violations = []

    # 1. Audit Dockerfiles
    for df_name in ["Dockerfile", "Dockerfile.test"]:
        df_path = ROOT / df_name
        if not df_path.is_file():
            continue
        content = df_path.read_text(encoding="utf-8")
        for line_no, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if line.startswith("FROM "):
                parts = line.split()
                if len(parts) >= 2:
                    image = parts[1]
                    if ":" not in image or image.endswith(":latest"):
                        violations.append(f"{df_name}:{line_no}: Image '{image}' uses forbidden :latest or lacks explicit tag")

    # 2. Audit Compose configuration
    config = get_compose_config("docker-compose.yml")
    services = config.get("services", {})
    for svc_name, svc_conf in services.items():
        image = svc_conf.get("image")
        if image:
            if ":" not in image or image.endswith(":latest"):
                violations.append(f"docker-compose.yml (service '{svc_name}'): image '{image}' is forbidden (:latest or untagged)")

    if violations:
        raise VerificationFailure("\n".join(violations))


def check_non_root():
    """Rule 2: Forbid running application containers as root (UID 0)."""
    df_path = ROOT / "Dockerfile"
    if not df_path.is_file():
        raise VerificationFailure("Dockerfile missing")

    content = df_path.read_text(encoding="utf-8")
    user_directives = [line.strip() for line in content.splitlines() if line.strip().startswith("USER ")]

    if not user_directives:
        raise VerificationFailure("Dockerfile does not define a USER directive; container runs as root by default")

    last_user = user_directives[-1].split(maxsplit=1)[1].strip()
    if last_user in ("root", "0"):
        raise VerificationFailure(f"Dockerfile explicitly sets USER to '{last_user}' (root execution forbidden)")

    # If app container is currently running, verify its runtime process UID
    try:
        proc = subprocess.run(
            ["docker", "compose", "ps", "-q", "app"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT, text=True
        )
        c_ids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        for cid in c_ids:
            uid_proc = subprocess.run(
                ["docker", "inspect", "--format", "{{.Config.User}}", cid],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT, text=True
            )
            runtime_user = uid_proc.stdout.strip()
            if runtime_user in ("root", "0", ""):
                raise VerificationFailure(f"Running container {cid[:12]} configured as user '{runtime_user}'")
    except VerificationFailure:
        raise
    except Exception:
        pass


def check_no_secrets_in_image():
    """Rule 3: Forbid embedding secrets into Dockerfile."""
    df_path = ROOT / "Dockerfile"
    content = df_path.read_text(encoding="utf-8")

    forbidden_patterns = [
        r"^ENV\s+.*PASSWORD\s*=",
        r"^ENV\s+.*SECRET_KEY\s*=",
        r"^ENV\s+.*TOKEN\s*=",
        r"^ENV\s+.*API_KEY\s*=",
    ]

    violations = []
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        for pattern in forbidden_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                violations.append(f"Dockerfile:{line_no}: Hardcoded secret in ENV directive: {line}")

    if violations:
        raise VerificationFailure("\n".join(violations))


def check_healthchecks():
    """Rule 4: Forbid disabling or omitting healthchecks on Compose services."""
    config = get_compose_config("docker-compose.yml")
    services = config.get("services", {})

    violations = []
    mandatory_services = ["db", "app", "nginx"]
    for svc_name in mandatory_services:
        if svc_name not in services:
            violations.append(f"Mandatory service '{svc_name}' missing from docker-compose.yml")
            continue

        svc = services[svc_name]
        hc = svc.get("healthcheck")
        if not hc:
            violations.append(f"Service '{svc_name}' has no healthcheck configured")
            continue

        test = hc.get("test")
        if not test or test == ["NONE"] or test == "NONE":
            violations.append(f"Service '{svc_name}' has disabled or empty healthcheck")

    if violations:
        raise VerificationFailure("\n".join(violations))


def check_ports_security():
    """Rule 5: Forbid unnecessary published ports (DB port and direct app access)."""
    config = get_compose_config("docker-compose.yml")
    services = config.get("services", {})

    violations = []

    # Database service must never publish ports to host
    db_ports = services.get("db", {}).get("ports")
    if db_ports:
        violations.append(f"Security violation: 'db' service publishes ports to host: {db_ports}")

    # Application service direct host access must be forbidden when fronted by Nginx
    app_ports = services.get("app", {}).get("ports")
    if app_ports:
        violations.append(f"Architecture violation: 'app' service publishes ports directly to host: {app_ports} (must be proxied via Nginx)")

    # Only nginx should publish host ports
    nginx_ports = services.get("nginx", {}).get("ports")
    if not nginx_ports:
        violations.append("Reverse proxy 'nginx' does not publish any port to host")

    if violations:
        raise VerificationFailure("\n".join(violations))


def check_resource_limits():
    """Rule 6: Ensure sensible resource limits are defined on all services."""
    config = get_compose_config("docker-compose.yml")
    services = config.get("services", {})

    violations = []
    for svc_name in ["db", "app", "nginx"]:
        svc = services.get(svc_name, {})
        limits = svc.get("deploy", {}).get("resources", {}).get("limits", {})
        if not limits or not limits.get("cpus") or not limits.get("memory"):
            violations.append(f"Service '{svc_name}' lacks explicit CPU and/or memory resource limits")

    if violations:
        raise VerificationFailure("\n".join(violations))


def check_graceful_shutdown():
    """Rule 7: Verify graceful shutdown configuration in Dockerfile."""
    df_path = ROOT / "Dockerfile"
    content = df_path.read_text(encoding="utf-8")

    has_stopsignal = any(line.strip().startswith("STOPSIGNAL ") for line in content.splitlines())
    has_exec_cmd = any(re.match(r'^CMD\s+\[.*\]', line.strip()) for line in content.splitlines())

    if not has_stopsignal:
        raise VerificationFailure("Dockerfile lacks STOPSIGNAL directive for graceful shutdown")
    if not has_exec_cmd:
        raise VerificationFailure("Dockerfile does not use exec form for CMD (required for PID 1 signal trapping)")


def main():
    print("=================================================================")
    print("      LAB 4 AUTOMATED CONTAINER ENVIRONMENT AUDIT (GATE)        ")
    print("=================================================================")

    checks = [
        ("Tag policy: no ':latest' or untagged base images", check_no_latest),
        ("User policy: non-root execution enforced", check_non_root),
        ("Secret policy: no secrets hardcoded into images", check_no_secrets_in_image),
        ("Healthcheck policy: active healthchecks required", check_healthchecks),
        ("Port exposure policy: DB isolated, App direct access forbidden", check_ports_security),
        ("Resource policy: CPU and memory limits defined", check_resource_limits),
        ("Graceful shutdown policy: STOPSIGNAL and exec CMD configured", check_graceful_shutdown),
    ]

    all_passed = True
    for name, func in checks:
        try:
            func()
            log_step(name, True)
        except VerificationFailure as e:
            log_step(name, False, str(e))
            all_passed = False
        except Exception as e:
            log_step(name, False, f"Unexpected error: {e}")
            all_passed = False

    print("-----------------------------------------------------------------")
    if all_passed:
        print("[SUCCESS] All container operational requirements satisfied!")
        sys.exit(0)
    else:
        print("[REJECTED] Container configuration violated operational requirements.")
        sys.exit(1)


if __name__ == "__main__":
    main()
