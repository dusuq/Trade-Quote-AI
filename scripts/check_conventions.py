#!/usr/bin/env python3
"""Automated convention guard for TradeQuote AI backend services.

Enforces the machine-checkable rules in docs/07-SERVICE-CONVENTIONS.md so that
architectural drift fails CI instead of relying on a human reviewer catching it.
Stdlib only — runs anywhere, no dependencies.

Exit code 0 = all good; 1 = one or more violations (printed).

Run locally:  python scripts/check_conventions.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = REPO_ROOT / "services"

# Only this service may verify/decode JWTs — it is the token authority.
JWT_ALLOWLIST = {"auth-service"}

# Patterns that indicate a service is decoding JWTs itself (the forbidden pattern).
JWT_IMPORT_RE = re.compile(r"^\s*import\s+jwt\b|^\s*from\s+jwt\b", re.MULTILINE)
JWT_DECODE_RE = re.compile(r"\bjwt\.decode\s*\(")


def _iter_service_py_files(service_dir: Path):
    app_dir = service_dir / "app"
    if not app_dir.is_dir():
        return
    for path in app_dir.rglob("*.py"):
        if "__pycache__" in path.parts or ".venv" in path.parts:
            continue
        yield path


def check_jwt_boundary(violations: list[str]) -> None:
    """No service except the allowlist may import/decode JWTs (Convention section 1)."""
    for service_dir in sorted(p for p in SERVICES_DIR.iterdir() if p.is_dir()):
        if service_dir.name in JWT_ALLOWLIST:
            continue
        for py in _iter_service_py_files(service_dir):
            text = py.read_text(encoding="utf-8", errors="ignore")
            if JWT_IMPORT_RE.search(text) or JWT_DECODE_RE.search(text):
                rel = py.relative_to(REPO_ROOT)
                violations.append(
                    f"[auth-boundary] {rel}: service '{service_dir.name}' decodes JWT. "
                    f"Downstream services MUST trust the gateway's x-tenant-id header instead "
                    f"(docs/07-SERVICE-CONVENTIONS.md section 1)."
                )


def check_tooling_config(violations: list[str]) -> None:
    """Each service with a pyproject.toml must declare ruff + mypy (Convention §7)."""
    for service_dir in sorted(p for p in SERVICES_DIR.iterdir() if p.is_dir()):
        pyproject = service_dir / "pyproject.toml"
        if not pyproject.is_file():
            continue
        text = pyproject.read_text(encoding="utf-8", errors="ignore")
        if "[tool.ruff]" not in text:
            violations.append(
                f"[tooling] {pyproject.relative_to(REPO_ROOT)}: missing [tool.ruff] config (section 7)."
            )
        if "[tool.mypy]" not in text:
            violations.append(
                f"[tooling] {pyproject.relative_to(REPO_ROOT)}: missing [tool.mypy] config (section 7)."
            )


def main() -> int:
    if not SERVICES_DIR.is_dir():
        print("check_conventions: no services/ directory — nothing to check.")
        return 0

    violations: list[str] = []
    check_jwt_boundary(violations)
    check_tooling_config(violations)

    if violations:
        print("FAIL: convention violations found:\n")
        for v in violations:
            print(f"  - {v}")
        print(
            f"\n{len(violations)} violation(s). See docs/07-SERVICE-CONVENTIONS.md. "
            "Fix before merge."
        )
        return 1

    print("OK: all service conventions satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
