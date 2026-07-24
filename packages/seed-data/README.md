# 📦 @tradequote/seed-data — Trade Seed & Fixture Generator

This package provides realistic seed data catalogs and fixture generation tools for TradeQuote AI. It includes sample pricebook datasets across three primary contractor trades:

1. **Electrical** (`pricebooks/electrical.csv`) — Panels, Romex wiring, GFCI outlets, LED lighting, EV charger kits, master/journeyman labor rates, bucket trucks.
2. **Plumbing** (`pricebooks/plumbing.csv`) — Tankless & tank water heaters, PEX tubing, copper piping, toilets, faucets, drain clearing, sewer cameras, hydro-jetters.
3. **HVAC** (`pricebooks/hvac.csv`) — 3-ton heat pumps, air handlers, heat strips, smart thermostats, R-410A refrigerant, flex ducting, EPA tech labor, vacuum pumps.

---

## 🚀 Quickstart

### 1. Validate Trade CSV Catalogs
```bash
python packages/seed-data/generate_seeds.py --validate
```

### 2. Export JSON Test Fixtures
```bash
python packages/seed-data/generate_seeds.py --export-json
```

### 3. Seed Live Pricebook Service via HTTP API
```bash
python packages/seed-data/generate_seeds.py --seed-url http://localhost:8004 --tenant-id 11111111-1111-1111-1111-111111111111
```

---

## 📊 CSV Schema Specification

| Header | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `kind` | `material \| labor \| equipment` | Item classification | `material` |
| `name` | `string` | Display name of the item/labor | `12/2 NMB Romex Wire (250ft)` |
| `sku` | `string` | Unique SKU per tenant | `ELE-WIR-122-250` |
| `description` | `string` | Detailed specifications | `12 AWG copper wire with ground` |
| `unit` | `string` | Unit of measure (`each`, `hour`, `roll`, `flat`, `day`) | `roll` |
| `unit_cost_minor` | `integer` | Unit cost in minor units / cents | `11200` ($112.00) |
| `default_markup_bps` | `integer` | Default markup in basis points (10000 = 100%) | `3500` (35%) |
| `currency` | `string` | ISO-4217 3-letter currency code | `USD` |
