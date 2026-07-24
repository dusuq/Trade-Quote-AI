#!/usr/bin/env python3
"""TradeQuote AI — Trade Pricebook Seed & Fixture Generator.

Usage:
    python generate_seeds.py --validate
    python generate_seeds.py --export-json
    python generate_seeds.py --seed-url http://localhost:8004 --tenant-id <UUID>
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from pathlib import Path
from typing import Any

SEED_DIR = Path(__file__).parent / "pricebooks"
VALID_KINDS = {"material", "labor", "equipment"}
REQUIRED_HEADERS = {"kind", "name", "sku", "description", "unit", "unit_cost_minor", "default_markup_bps", "currency"}


def validate_trade_csv(csv_path: Path) -> tuple[bool, list[str]]:
    """Validates a trade pricebook CSV file against required headers and schema constraints."""
    errors: list[str] = []
    if not csv_path.exists():
        return False, [f"File {csv_path} does not exist."]

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])

        missing = REQUIRED_HEADERS - headers
        if missing:
            errors.append(f"{csv_path.name}: Missing required headers: {sorted(missing)}")
            return False, errors

        for idx, row in enumerate(reader, start=2):
            kind = (row.get("kind") or "").strip().lower()
            name = (row.get("name") or "").strip()
            cost_str = (row.get("unit_cost_minor") or "").strip()
            markup_str = (row.get("default_markup_bps") or "").strip()

            if kind not in VALID_KINDS:
                errors.append(f"{csv_path.name} Row {idx}: Invalid kind '{kind}'. Must be in {VALID_KINDS}")
            if not name:
                errors.append(f"{csv_path.name} Row {idx}: 'name' cannot be empty")
            try:
                cost = int(cost_str)
                if cost < 0:
                    errors.append(f"{csv_path.name} Row {idx}: unit_cost_minor must be >= 0")
            except ValueError:
                errors.append(f"{csv_path.name} Row {idx}: unit_cost_minor '{cost_str}' must be integer")

            try:
                markup = int(markup_str)
                if markup < 0:
                    errors.append(f"{csv_path.name} Row {idx}: default_markup_bps must be >= 0")
            except ValueError:
                errors.append(f"{csv_path.name} Row {idx}: default_markup_bps '{markup_str}' must be integer")

    return len(errors) == 0, errors


def export_trade_json(csv_path: Path, output_dir: Path) -> Path:
    """Converts a trade CSV pricebook into a JSON fixture file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append({
                "kind": row["kind"].strip().lower(),
                "name": row["name"].strip(),
                "sku": row["sku"].strip() or None,
                "description": row["description"].strip() or None,
                "unit": row["unit"].strip() or "each",
                "unit_cost_minor": int(row["unit_cost_minor"]),
                "default_markup_bps": int(row["default_markup_bps"]),
                "currency": row["currency"].strip().upper() or "USD",
                "is_active": True,
            })

    json_path = output_dir / f"{csv_path.stem}.json"
    with open(json_path, mode="w", encoding="utf-8") as out:
        json.dump(items, out, indent=2)

    return json_path


def seed_via_http(service_url: str, tenant_id: str, csv_path: Path) -> dict[str, Any]:
    """Posts a trade CSV file to pricebook-service /v1/pricebook/import endpoint."""
    import urllib.request

    url = f"{service_url.rstrip('/')}/v1/pricebook/import"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

    with open(csv_path, "rb") as f:
        file_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{csv_path.name}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "x-tenant-id": tenant_id,
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="TradeQuote AI — Seed Data & Trade Pricebook Generator")
    parser.add_argument("--validate", action="store_true", help="Validate all trade pricebook CSV files")
    parser.add_argument("--export-json", action="store_true", help="Export trade pricebooks to JSON fixtures")
    parser.add_argument("--seed-url", type=str, help="Pricebook service HTTP URL (e.g. http://localhost:8004)")
    parser.add_argument("--tenant-id", type=str, default=str(uuid.uuid4()), help="Tenant UUID for seeding")

    args = parser.parse_args()

    csv_files = list(SEED_DIR.glob("*.csv"))
    if not csv_files:
        print(f"No CSV trade pricebooks found in {SEED_DIR}")
        sys.exit(1)

    print(f"Found {len(csv_files)} trade pricebook catalogs: {[f.name for f in csv_files]}")

    all_ok = True
    for csv_file in csv_files:
        valid, errors = validate_trade_csv(csv_file)
        if valid:
            print(f"  [OK] {csv_file.name}: Valid")
        else:
            all_ok = False
            print(f"  [FAIL] {csv_file.name}: Invalid")
            for err in errors:
                print(f"    - {err}")

    if not all_ok:
        print("\nValidation failed!")
        sys.exit(1)

    if args.export_json:
        out_dir = SEED_DIR.parent / "fixtures"
        for csv_file in csv_files:
            json_file = export_trade_json(csv_file, out_dir)
            print(f"  [Exported] {json_file}")

    if args.seed_url:
        for csv_file in csv_files:
            print(f"  Seeding {csv_file.name} to {args.seed_url} (tenant: {args.tenant_id})...")
            try:
                res = seed_via_http(args.seed_url, args.tenant_id, csv_file)
                print(f"  [Imported] created={res.get('created')}, updated={res.get('updated')}, total={res.get('total_rows')}")
            except Exception as exc:
                print(f"  [Failed] seeding {csv_file.name}: {exc}")

    print("\nComplete!")


if __name__ == "__main__":
    main()
