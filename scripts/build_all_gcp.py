#!/usr/bin/env python3
"""Build all 12 TradeQuote AI container images using GCP Cloud Build.

11 Python services (context = services/<name>)
1 API Gateway (context = repository root, dockerfile = apps/api-gateway/Dockerfile)
"""

import os
import subprocess
import sys

PROJECT_ID = "appdusuqerp"
REGION = "us-east1"
REPO = "tradequote"

SERVICES = [
    "auth-service",
    "customer-service",
    "pricebook-service",
    "quote-service",
    "proposal-service",
    "esign-service",
    "ai-service",
    "analytics-service",
    "notification-service",
    "integration-service",
    "payment-service",
]

def main() -> None:
    print(f"=== Starting build of 12 container images on GCP Cloud Build ({PROJECT_ID}) ===")
    results = {}

    # 1. Build Python services
    for svc in SERVICES:
        tag = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}/{svc}:test"
        src_dir = os.path.join("services", svc)
        print(f"\n--- Building {svc} from {src_dir} ---")
        cmd = f'gcloud builds submit "{src_dir}" --tag "{tag}" --quiet'
        res = subprocess.run(cmd, shell=True)
        results[svc] = res.returncode == 0
        if res.returncode != 0:
            print(f"[FAILED]: {svc}")
        else:
            print(f"[SUCCESS]: {svc}")

    # 2. Build API Gateway (context = repo root)
    svc = "api-gateway"
    tag = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}/{svc}:test"
    dockerfile = "apps/api-gateway/Dockerfile"
    print(f"\n--- Building {svc} from repository root (Dockerfile={dockerfile}) ---")
    cmd = f'gcloud builds submit . --tag "{tag}" -f "{dockerfile}" --quiet'
    res = subprocess.run(cmd, shell=True)
    results[svc] = res.returncode == 0
    if res.returncode != 0:
        print(f"❌ FAILED: {svc}")
    else:
        print(f"✅ SUCCESS: {svc}")

    print("\n" + "=" * 50)
    print("=== SUMMARY OF IMAGE BUILDS ===")
    all_passed = True
    for svc, ok in results.items():
        status_str = "[PASSED]" if ok else "[FAILED]"
        print(f"  {svc:25s}: {status_str}")
        if not ok:
            all_passed = False

    if not all_passed:
        sys.exit(1)
    print("All 12 images built successfully!")

if __name__ == "__main__":
    main()
