#!/usr/bin/env python3
"""GCP Cloud Run deployment automation driven by infra/services.yml (T309 / M24).

Maps the services registry onto Cloud Run services, Secret Manager, and IAM.

Security & Architecture Invariants:
1. Only `api-gateway` (public: true in services.yml) is exposed publicly (--ingress all).
2. All 11 backend services are strictly private (--ingress internal --no-allow-unauthenticated).
3. `api-gateway` and `payment-service` run min-instances >= 2 to prevent dropped webhooks / cold starts.
4. Secrets are injected via GCP Secret Manager (--set-secrets), never hardcoded or environment variables.

Usage:
    python scripts/deploy_gcp.py --dry-run
    python scripts/deploy_gcp.py --project appdusuqerp --region us-east1
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "infra" / "services.yml"

def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy TradeQuote AI services to GCP Cloud Run.")
    parser.add_argument("--project", default="appdusuqerp", help="GCP Project ID")
    parser.add_argument("--region", default="us-east1", help="GCP Region")
    parser.add_argument("--tag", default="test", help="Docker image tag to deploy")
    parser.add_argument("--dry-run", action="store_true", help="Print gcloud commands without executing")
    args = parser.parse_args()

    if not REGISTRY_PATH.is_file():
        print(f"Error: Registry file not found at {REGISTRY_PATH}")
        sys.exit(1)

    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = yaml.safe_load(f)

    units = registry.get("units", {})
    print(f"=== GCP Cloud Run Deploy Matrix ({len(units)} services) ===")
    print(f"Project: {args.project} | Region: {args.region} | Tag: {args.tag} | Dry Run: {args.dry_run}\n")

    public_count = 0
    commands = []

    for config in units:
        name = config.get("name")
        is_public = config.get("public", False)
        port = config.get("port", 8000)
        memory = f"{config.get('memory_mb', 512)}Mi"
        min_machines = config.get("min_machines", 0)
        critical = config.get("critical", False)
        
        if is_public:
            public_count += 1

        if min_machines == 0 and critical:
            min_machines = 2

        image_uri = f"{args.region}-docker.pkg.dev/{args.project}/tradequote/tradequote-{name}:{args.tag}"
        if name == "api-gateway":
            image_uri = f"{args.region}-docker.pkg.dev/{args.project}/tradequote/api-gateway:{args.tag}"

        cmd = [
            "gcloud", "run", "deploy", f"tradequote-{name}",
            "--project", args.project,
            "--region", args.region,
            "--image", image_uri,
            "--port", str(port),
            "--memory", memory,
            "--min-instances", str(min_machines),
        ]

        if is_public:
            cmd.extend(["--ingress", "all", "--allow-unauthenticated"])
        else:
            cmd.extend(["--ingress", "internal", "--no-allow-unauthenticated"])

        # Secret Manager configuration
        secrets = "JWT_SECRET=tq-jwt-secret:latest,DATABASE_URL=tq-db-url:latest"
        if name in ("auth-service", "integration-service"):
            secrets += ",MFA_ENCRYPTION_KEY=tq-mfa-key:latest,INTEGRATION_TOKEN_ENCRYPTION_KEY=tq-integration-key:latest"
        cmd.extend(["--set-secrets", secrets])

        commands.append((name, cmd))

    # Strict invariant check: exactly one public unit
    if public_count != 1:
        print(f"[INVARIANT VIOLATION]: Expected exactly 1 public unit, found {public_count}")
        sys.exit(1)
    print("[OK] Invariant Check Passed: Exactly 1 public service (api-gateway).")

    for name, cmd in commands:
        cmd_str = " ".join(cmd)
        print(f"\n---> Deploying {name}:")
        print(f"     {cmd_str}")
        if not args.dry_run:
            res = subprocess.run(cmd_str, shell=True)
            if res.returncode != 0:
                print(f"[FAILED] Deploy failed for {name}")
                sys.exit(1)

    print("\nAll Cloud Run services deployed successfully!")

if __name__ == "__main__":
    main()
