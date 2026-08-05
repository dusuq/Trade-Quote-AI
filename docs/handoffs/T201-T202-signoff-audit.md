# CTO Sign-off — T201 (AI Quote Assistant) & T202 (AI Copilot)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-07-30
- **Verdict:** ✅ **Both signed off.** T202 is the cleanest agent-delivered task audited in this
  session — every substantive claim in its spec independently checked out, including the two that
  usually don't. Declared gaps carry forward as tracked follow-ups, not surprises.

---

## Scope note: T201 is my own work

I built T201, so signing it off is a weaker check than an independent audit and shouldn't be
presented otherwise. The genuinely new information here is **regression**: T202 modified six files
T201 owns (`config.py`, `domain/models.py`, `domain/protocols.py`, `interface/deps.py`,
`interface/schemas.py`, `interface/routes.py`, plus both test helpers). What I can usefully verify is
that T201 still holds after that, and it does — its 120 tests all still pass inside the combined
185, with lint, types, and the conventions guard clean.

---

## T202 — what was independently verified

Every row was re-run or read here, not taken from the spec:

| Claim                                                | Verified                                                                                                                                      |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `pytest` — 185 passed (120 T201 regression + 65 new) | **185 passed**, and the arithmetic matches exactly                                                                                            |
| `ruff check app tests` clean                         | clean                                                                                                                                         |
| `mypy app` clean                                     | clean, 41 source files                                                                                                                        |
| `check_conventions.py` green                         | OK                                                                                                                                            |
| **"No gateway change needed"**                       | **True** — the gateway diff in the tree is T205's notification route, not T202's. Copilot correctly rides T201's existing `/v1/ai` proxy      |
| **"Read-only — never mutates a quote"**              | **True** — grepped every copilot application/infrastructure path for `POST`/`PUT`/`PATCH`/`DELETE`: zero hits                                 |
| **"Margin math is local, not LLM"**                  | **True** — `application/margin.py` is pure integer/`Decimal` arithmetic; the model is trusted only for `suggested_markup_bps` and `reasoning` |
| Runs on `claude-sonnet-5`                            | Confirmed in `Settings.copilot_model`; a valid current model ID                                                                               |
| Structured outputs used                              | Confirmed (`output_config` with a JSON schema)                                                                                                |
| Metered under `feature: "copilot"`                   | `AiFeature.COPILOT = "copilot"`, matching `AiUsageRecordedPayload.feature` in `packages/types`                                                |

### Three things it got right that were easy to get wrong

1. **No `temperature` anywhere.** Grepping the whole service for `temperature`/`top_p`/`top_k`
   returns only my own explanatory comment in `config.py`. The T201 plan had specified
   `temperature: 0.1`, which current models reject with a 400 — T202 did not reintroduce it.
2. **ADR-0003 rule 3 is respected.** All three copilot routes go through `_run_metered`, so no
   blocking LLM or HTTP call runs inside an open database transaction. That is the rule T307b broke,
   and it was followed here without being restated.
3. **Refusal handling.** `stop_reason == "refusal"` is checked before reading `response.content`,
   mapped to `CopilotAnalysisError` → 422. Code that indexes `content[0]` unconditionally breaks on
   a refusal; this doesn't.

Also good, unprompted: `HttpQuoteReader` maps quote-service's 404 to `QuoteNotFoundError` for both a
missing quote _and_ another tenant's quote, with a comment noting the deliberate non-leak; and
`rewrite` rejects a response whose text count doesn't match the input (→ 422) rather than silently
returning misaligned advice.

---

## Findings — non-blocking

### 1. `_infer_trade_hint` keyword ordering misclassifies solar

`quote_reader.py`'s `_TRADE_KEYWORDS` is scanned first-hit-wins, and `("panel", "electrical")`
precedes `("solar", "solar")`. So a quote titled _"Solar panel installation"_ infers
`trade_hint = "electrical"`.

Low severity by design — the hint is explicitly advisory and the model re-classifies from the actual
line items — but it is a real ordering bug. Moving the `solar` entries above `panel` fixes it.

### 2. `margin_bps` / `markup_bps` compute a rate through float

```python
return round((revenue_minor - cost_minor) * _BPS / revenue_minor)
```

`/` is float division and `round()` is banker's rounding, so a result can land ±1 bps from the
integer-exact value. Immaterial in practice — these are advisory display rates, not money, and float64
has ample precision at realistic quote magnitudes — but it is inconsistent with the
integer-money discipline the rest of the module holds to. `(a * _BPS + b // 2) // b` would be exact.

### 3. The 97% coverage claim is unverified, not disputed

No coverage tooling is installed in the service venv (`pytest --cov` and `python -m coverage` both
unavailable), so I could not reproduce the "95–100% / 97% across the copilot surface" figure. The
test _count_ and everything else checked out, and the new tests plainly exercise the copilot surface,
so this is recorded as **unverified** rather than doubted. Adding `pytest-cov` to the dev extras
would make it checkable.

---

## Fixed during this audit

`.gitignore` had `coverage/` but not the bare `.coverage` data file Python's coverage tool actually
writes, so two stray `.coverage` artifacts were sitting untracked in service directories. Added
`.coverage` and `.coverage.*`.

---

## Carried-forward gaps (declared, not discovered)

Both tasks declared their own limits, which is why these are follow-ups rather than findings:

| Gap                                                                                   | Tracked as           |
| ------------------------------------------------------------------------------------- | -------------------- |
| T201 has no web UI                                                                    | **T201b**            |
| T202 has no web UI (copilot panel on the quote builder)                               | **T202b** (new)      |
| T201 has no idempotency key — a retried `voice-to-quote` creates a second draft quote | M15 spec §6          |
| Neither service's RLS (`ai_usage_log`) has run against live Postgres                  | **T311b**            |
| Copilot prompt quality is unmeasured — no eval set scores real quotes                 | M25 (test/eval work) |

## Unrelated observation

`notification-service` (T205) is **not registered in `scripts/run_all_tests.py`**, so the
"all services pass" sweep does not actually cover it. Not a T201/T202 issue, but it means the sweep
currently under-reports scope — worth fixing when T205 is reviewed.
