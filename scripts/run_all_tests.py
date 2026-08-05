#!/usr/bin/env python3
"""Master Test Runner for the backend microservices (T207, extended T313).

Runs pytest + ruff + mypy in every service listed in SERVICE_DIRS below, which
must stay in lockstep with the directories in services/ — a service missing
from that list is a service the sweep silently never checked (that was the
notification-service gap found in T205, and the integration-service gap found
in the T30x batch audit). tests/infra/test_sweep_coverage.py now fails if the
two ever diverge again, rather than leaving it to whoever next reads this file.

**The commands below deliberately mirror .github/workflows/ci.yml's Python
lane byte-for-byte** (`ruff check .`, `mypy .`, `pytest`). That parity is the
point, not an accident:

    T313 found this runner using `ruff check app` while CI used `ruff check .`.
    So the sweep reported "all services passed" while never linting a single
    line of test code — and CI, which *did* lint it, was already red on
    analytics-service. A local gate that is weaker than the remote one is
    worse than no local gate: it actively manufactures false confidence.

If you change a command here, change it in ci.yml too (and vice versa).
tests/infra/test_sweep_coverage.py asserts they still agree.

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
    ROOT_DIR / "services" / "proposal-service",
    ROOT_DIR / "services" / "analytics-service",
    ROOT_DIR / "services" / "esign-service",
    ROOT_DIR / "services" / "ai-service",
    ROOT_DIR / "services" / "notification-service",
    ROOT_DIR / "services" / "payment-service",
    ROOT_DIR / "services" / "integration-service",
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
    res_test = subprocess.run(cmd_test, cwd=service_dir, capture_output=True, text=True, check=False)
    results["pytest"] = (res_test.returncode == 0, res_test.stdout + "\n" + res_test.stderr)
    print(f"  pytest: {'[PASSED]' if res_test.returncode == 0 else '[FAILED]'}")

    # 2. Ruff Linting
    # `.` not `app` (T313): linting only app/ meant no service's tests/ was
    # ever linted by this sweep. `.` also covers conftest.py and anything else
    # at the service root, and matches CI exactly. Ruff excludes .venv itself.
    print(f"[{service_dir.name}] Running ruff code quality checks...")
    cmd_ruff = [ruff_cmd, "check", "."]
    res_ruff = subprocess.run(cmd_ruff, cwd=service_dir, capture_output=True, text=True, check=False)
    results["ruff"] = (res_ruff.returncode == 0, res_ruff.stdout + "\n" + res_ruff.stderr)
    print(f"  ruff  : {'[PASSED]' if res_ruff.returncode == 0 else '[FAILED]'}")

    # 3. Mypy Typechecking
    # `.` for the same CI-parity reason. Note this is NOT equivalent to adding
    # tests to the typechecker: 10 of the 11 services set `exclude = [...,
    # "tests"]` in their [tool.mypy], so `.` and `app` resolve to the same file
    # set for them. Typechecking test code is a separate decision that belongs
    # in the conventions doc, not a silent side effect of this line.
    print(f"[{service_dir.name}] Running mypy typechecks...")
    cmd_mypy = [mypy_cmd, "."]
    res_mypy = subprocess.run(cmd_mypy, cwd=service_dir, capture_output=True, text=True, check=False)
    results["mypy"] = (res_mypy.returncode == 0, res_mypy.stdout + "\n" + res_mypy.stderr)
    print(f"  mypy  : {'[PASSED]' if res_mypy.returncode == 0 else '[FAILED]'}")

    return results


def run_repo_root_lint() -> dict[str, tuple[bool, str]]:
    """Lint repo-root Python: tests/ and scripts/ (T313).

    These live outside services/, so no service pyproject.toml is an ancestor
    of them and none of the per-service lint runs above ever touched them —
    including tests/infra and tests/security, both of which CI *executes*.
    The repo-root ruff.toml is what governs this lane; see its header for why
    it names its rules explicitly instead of inheriting ruff's defaults.

    Any service venv's ruff works here — config comes from ruff.toml, not from
    whichever interpreter invoked it — so this reuses the first one available
    rather than requiring a separate root toolchain install.
    """
    for service_dir in SERVICE_DIRS:
        for candidate in (
            service_dir / ".venv" / "Scripts" / "ruff.exe",
            service_dir / ".venv" / "bin" / "ruff",
        ):
            if candidate.exists():
                ruff_cmd = str(candidate)
                break
        else:
            continue
        break
    else:
        ruff_cmd = "ruff"

    print("\n[repo-root] Linting tests/ and scripts/...")
    res = subprocess.run(
        [ruff_cmd, "check", "tests", "scripts"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"  ruff  : {'[PASSED]' if res.returncode == 0 else '[FAILED]'}")
    return {"ruff": (res.returncode == 0, res.stdout + "\n" + res.stderr)}


def main() -> None:
    print("TradeQuote AI — Master Backend Test & Lint Runner (T207 / T313)\n")

    results: dict[str, dict[str, tuple[bool, str]]] = {}

    for service_dir in SERVICE_DIRS:
        if not service_dir.exists():
            print(f"Skipping {service_dir.name} (directory missing)")
            continue

        results[service_dir.name] = run_service_checks(service_dir)

    results["repo-root (tests/, scripts/)"] = run_repo_root_lint()

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
