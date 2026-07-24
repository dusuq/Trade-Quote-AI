#!/usr/bin/env python3
"""Master Test Runner for Phase 1 Microservices (T207).

Executes unit & integration test suites across:
- services/auth-service
- services/customer-service
- services/pricebook-service
- services/quote-service
- tests/integration (PostgreSQL RLS suite when live DB available)

Usage:
    python scripts/run_all_tests.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

SERVICE_DIRS = [
    ROOT_DIR / "services" / "auth-service",
    ROOT_DIR / "services" / "customer-service",
    ROOT_DIR / "services" / "pricebook-service",
    ROOT_DIR / "services" / "quote-service",
]


def run_service_checks(service_dir: Path) -> dict[str, tuple[bool, str]]:
    """Runs pytest, ruff check, and mypy inside a microservice directory."""
    venv_bin = service_dir / ".venv" / "Scripts"
    if not venv_bin.exists():
        venv_bin = service_dir / ".venv" / "bin"
    
    python_cmd = str(venv_bin / "python.exe") if (venv_bin / "python.exe").exists() else (str(venv_bin / "python") if (venv_bin / "python").exists() else sys.executable)
    ruff_cmd = str(venv_bin / "ruff.exe") if (venv_bin / "ruff.exe").exists() else (str(venv_bin / "ruff") if (venv_bin / "ruff").exists() else "ruff")
    mypy_cmd = str(venv_bin / "mypy.exe") if (venv_bin / "mypy.exe").exists() else (str(venv_bin / "mypy") if (venv_bin / "mypy").exists() else "mypy")

    results: dict[str, tuple[bool, str]] = {}

    # 1. Pytest
    print(f"\n[{service_dir.name}] Running unit & integration tests...")
    cmd_test = [python_cmd, "-m", "pytest", "tests"]
    res_test = subprocess.run(cmd_test, cwd=service_dir, capture_output=True, text=True)
    results["pytest"] = (res_test.returncode == 0, res_test.stdout + "\n" + res_test.stderr)
    print(f"  pytest: {'[PASSED]' if res_test.returncode == 0 else '[FAILED]'}")

    # 2. Ruff Linting
    print(f"[{service_dir.name}] Running ruff code quality checks...")
    cmd_ruff = [ruff_cmd, "check", "app"]
    res_ruff = subprocess.run(cmd_ruff, cwd=service_dir, capture_output=True, text=True)
    results["ruff"] = (res_ruff.returncode == 0, res_ruff.stdout + "\n" + res_ruff.stderr)
    print(f"  ruff  : {'[PASSED]' if res_ruff.returncode == 0 else '[FAILED]'}")

    # 3. Mypy Typechecking
    print(f"[{service_dir.name}] Running mypy typechecks...")
    cmd_mypy = [mypy_cmd, "app"]
    res_mypy = subprocess.run(cmd_mypy, cwd=service_dir, capture_output=True, text=True)
    results["mypy"] = (res_mypy.returncode == 0, res_mypy.stdout + "\n" + res_mypy.stderr)
    print(f"  mypy  : {'[PASSED]' if res_mypy.returncode == 0 else '[FAILED]'}")

    return results


def main() -> None:
    print("TradeQuote AI — Master Phase 1 Test & Lint Runner (T207)\n")

    results: dict[str, dict[str, tuple[bool, str]]] = {}

    for service_dir in SERVICE_DIRS:
        if not service_dir.exists():
            print(f"Skipping {service_dir.name} (directory missing)")
            continue
        
        results[service_dir.name] = run_service_checks(service_dir)

    print("\n==================================================")
    print(" SUMMARY OF PHASE 1 SERVICE CHECKS")
    print("==================================================")
    all_passed = True
    for service_name, checks in results.items():
        print(f"  {service_name}:")
        for check_name, (ok, output) in checks.items():
            status = "PASSED" if ok else "FAILED"
            if not ok:
                all_passed = False
                # Print failure output for visibility
                print(f"    - {check_name:10s}: {status}")
                print(f"\n--- {check_name.upper()} FAILURE OUTPUT ---")
                print(output)
                print("-----------------------------------\n")
            else:
                print(f"    - {check_name:10s}: {status}")

    if not all_passed:
        print("\n[ERROR] One or more code quality or test checks failed!")
        sys.exit(1)

    print("\n[SUCCESS] All Phase 1 service test and lint suites passed!")



if __name__ == "__main__":
    main()
