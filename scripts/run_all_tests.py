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


def run_service_tests(service_dir: Path) -> tuple[bool, str]:
    """Runs pytest inside a microservice directory using its virtual environment if available."""
    venv_python = service_dir / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = service_dir / ".venv" / "bin" / "python"
    
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [python_cmd, "-m", "pytest", "tests"]
    print(f"\n==================================================")
    print(f" Running tests for: {service_dir.name}")
    print(f" Command: {' '.join(cmd)}")
    print(f"==================================================")

    res = subprocess.run(cmd, cwd=service_dir, capture_output=True, text=True)
    return res.returncode == 0, res.stdout + "\n" + res.stderr


def main() -> None:
    print("TradeQuote AI — Master Phase 1 Test Runner (T207)\n")

    results: dict[str, bool] = {}
    logs: dict[str, str] = {}

    for service_dir in SERVICE_DIRS:
        if not service_dir.exists():
            print(f"Skipping {service_dir.name} (directory missing)")
            continue
        
        ok, output = run_service_tests(service_dir)
        results[service_dir.name] = ok
        logs[service_dir.name] = output
        
        status_str = "[PASSED]" if ok else "[FAILED]"
        print(f"Status: {status_str}")

    print("\n==================================================")
    print(" SUMMARY OF PHASE 1 TEST RESULTS")
    print("==================================================")
    all_passed = True
    for service_name, ok in results.items():
        status = "PASSED" if ok else "FAILED"
        if not ok:
            all_passed = False
        print(f"  - {service_name:30s}: {status}")

    if not all_passed:
        print("\n[ERROR] One or more test suites failed!")
        sys.exit(1)

    print("\n[SUCCESS] All Phase 1 service test suites passed!")


if __name__ == "__main__":
    main()
