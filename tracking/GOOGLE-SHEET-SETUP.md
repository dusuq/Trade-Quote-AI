# 📊 Google Sheet Setup — TradeQuote AI Development Tracker

This is your live control panel to mark development state, start modules, and verify progress.
The data already exists in **[`PROGRESS-TRACKER.csv`](PROGRESS-TRACKER.csv)** — import it and add the
formatting/formulas below to make it interactive.

> ⚠️ A live Google Sheet can't be auto-created from this environment (it needs Google sign-in).
> These steps take ~3 minutes and give you a fully working sheet. Alternatively, tell me to create it
> once the Google Drive connector is authorized (via `/mcp` in an interactive session).

---

## Step 1 — Import

1. Go to **sheets.new** (creates a blank Google Sheet).
2. **File → Import → Upload → select `PROGRESS-TRACKER.csv`**.
3. Import location: **Replace current sheet**. Separator: **Comma**. → **Import data**.
4. Rename the tab to **`Build Tracker`**. Freeze row 1 (**View → Freeze → 1 row**).

## Step 2 — Columns (already in the CSV)

`Task ID · Module · Workstream · Phase · Owner Agent · Model · Priority · Status · Start Date · End Date · Dependencies · Quality Gates Passed · Notes`

## Step 3 — Status dropdown (data validation on column H)

Select `H2:H` → **Data → Data validation → Dropdown**, values:
`NOT_STARTED, IN_PROGRESS, BLOCKED, IN_REVIEW, DONE`

## Step 4 — Color rules (Format → Conditional formatting on `H2:H`)

| Value         | Background |
| ------------- | ---------- |
| `DONE`        | green      |
| `IN_PROGRESS` | yellow     |
| `IN_REVIEW`   | blue       |
| `BLOCKED`     | red        |
| `NOT_STARTED` | grey       |

## Step 5 — Add a `Dashboard` tab (new sheet) — paste these formulas

```
Total tasks           =COUNTA('Build Tracker'!A2:A)
Done                  =COUNTIF('Build Tracker'!H2:H,"DONE")
In progress           =COUNTIF('Build Tracker'!H2:H,"IN_PROGRESS")
Blocked               =COUNTIF('Build Tracker'!H2:H,"BLOCKED")
% Complete            =ROUND(COUNTIF('Build Tracker'!H2:H,"DONE")/COUNTA('Build Tracker'!A2:A)*100,1)&"%"

Phase 1 % done        =ROUND(COUNTIFS('Build Tracker'!D2:D,"Phase 1",'Build Tracker'!H2:H,"DONE")/COUNTIF('Build Tracker'!D2:D,"Phase 1")*100,1)&"%"

By agent (paste in A10):
=QUERY('Build Tracker'!E2:H, "select E, count(A) where H='DONE' group by E label count(A) 'Done'")
```

## Step 6 — Verify a build stage

- **What's ready to start now?** Filter `Status = NOT_STARTED` and cross-check `Dependencies` are all `DONE`.
  (Mirror of the "Check for Next Task" table in `TASKS.md`.)
- **Where is each agent?** Use the Dashboard "By agent" query.
- **Is a phase gate met?** Phase % done = 100% → run the phase exit criteria in `docs/10-ROADMAP.md`.

---

## Keeping it in sync

When you (or an agent) finish a task: set `Status = DONE`, fill `End Date`, check the box in `TASKS.md`.
Keep the CSV and the Sheet as mirrors — the CSV is the version-controlled source of truth in git.

## Suggested extra tabs

- **`Modules`** — one row per M0–M27 with rollup `=COUNTIFS` of task status → module-level % .
- **`Risks`** — risk register (id, description, likelihood, impact, mitigation, owner).
- **`Decisions`** — links to ADRs in `docs/adr/`.
