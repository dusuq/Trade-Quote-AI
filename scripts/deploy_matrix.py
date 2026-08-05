#!/usr/bin/env python3
"""Compute which deployable units changed, for the deploy workflow (T309 / M24).

Reads infra/services.yml, diffs the current commit against its parent, and emits
GitHub Actions outputs describing what needs to ship.

Outputs (written to $GITHUB_OUTPUT):
    any       "true" | "false"  — is there anything to deploy at all
    units     JSON array of every changed unit (name/path/port)
    services  JSON array of changed units EXCLUDING the gateway
    gateway   "true" | "false"  — does the public edge need redeploying

Why the gateway is separated: it is the only public entrypoint, so it must roll
*after* the services behind it. Splitting the matrix here keeps that ordering in
the workflow's job graph instead of in per-step `if:` conditions.

Shared-surface changes (the registry itself, the lockfile, packages/*, the root
tsconfig) force a full deploy — a change there can affect any unit, and guessing
which ones is how you ship a half-updated platform.

Env:
    FORCE_UNITS   "all", or a comma-separated list of unit names, to override
                  change detection (used by workflow_dispatch).
    GITHUB_OUTPUT path to the step-output file; prints to stdout when unset so
                  the script is runnable locally for debugging.

Usage (local):
    python scripts/deploy_matrix.py
    FORCE_UNITS=all python scripts/deploy_matrix.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "infra" / "services.yml"
GATEWAY = "api-gateway"

# A change to any of these can affect every unit, so they trigger a full deploy.
SHARED_PATHS = (
    "infra/services.yml",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "tsconfig.json",
    "packages/",
    "scripts/gen_infra.py",
)


def changed_files() -> list[str]:
    """Files changed in HEAD vs its parent.

    Falls back to an empty list on the very first commit (no parent), which
    correctly yields "nothing changed" rather than crashing the deploy.
    """
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        print("deploy_matrix: no parent commit to diff against — treating as no change.")
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def select_units(reg: dict[str, Any]) -> list[dict[str, Any]]:
    units = reg["units"]
    force = (os.environ.get("FORCE_UNITS") or "").strip()

    if force == "all":
        print("deploy_matrix: FORCE_UNITS=all — deploying every unit.")
        return list(units)

    if force:
        wanted = {n.strip() for n in force.split(",") if n.strip()}
        known = {u["name"] for u in units}
        unknown = wanted - known
        if unknown:
            print(f"deploy_matrix: ERROR unknown unit(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            print(f"deploy_matrix: known units: {', '.join(sorted(known))}", file=sys.stderr)
            raise SystemExit(1)
        print(f"deploy_matrix: FORCE_UNITS={force}")
        return [u for u in units if u["name"] in wanted]

    files = changed_files()
    if not files:
        return []

    if any(f.startswith(SHARED_PATHS) or f in SHARED_PATHS for f in files):
        hit = next(f for f in files if f.startswith(SHARED_PATHS) or f in SHARED_PATHS)
        print(f"deploy_matrix: shared surface changed ({hit}) — deploying every unit.")
        return list(units)

    selected = [u for u in units if any(f.startswith(u["path"] + "/") for f in files)]
    print(f"deploy_matrix: {len(files)} file(s) changed → {len(selected)} unit(s) to deploy.")
    return selected


def emit(outputs: dict[str, str]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    rendered = "\n".join(f"{k}={v}" for k, v in outputs.items())
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
    print("\ndeploy_matrix outputs:")
    print(rendered)


def main() -> int:
    with REGISTRY.open(encoding="utf-8") as fh:
        reg = yaml.safe_load(fh)

    selected = select_units(reg)

    def slim(u: dict[str, Any]) -> dict[str, Any]:
        # The matrix only needs what the deploy step interpolates.
        return {"name": u["name"], "path": u["path"], "port": u["port"]}

    services = [slim(u) for u in selected if u["name"] != GATEWAY]
    gateway = any(u["name"] == GATEWAY for u in selected)

    for u in selected:
        # ASCII only: this script runs on Windows consoles (cp1252) as well as
        # in CI, and a decorative arrow is not worth a UnicodeEncodeError.
        print(f"  - {u['name']} ({u['path']})")

    emit(
        {
            "any": "true" if selected else "false",
            "units": json.dumps([slim(u) for u in selected], separators=(",", ":")),
            "services": json.dumps(services, separators=(",", ":")),
            "gateway": "true" if gateway else "false",
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
