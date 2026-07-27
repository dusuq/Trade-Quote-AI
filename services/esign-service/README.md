# E-Signature Service (Module M10 / T204)

- **Owner Agent:** Agent 1 (CTO) — built at founder direction; board lane was A4
- **Bounded context:** `esign` (declared in `packages/types/src/events.ts`)
- **Depends on:** T203 Proposal Builder
- **Design spec:** [docs/modules/M10-esignature.md](../../docs/modules/M10-esignature.md)

Signature capture for proposals, with a **tamper-evident audit trail**. The audit trail is the
point: a feature that stores "signed: true" creates the appearance of enforceability without the
evidence to support it.

## What's here

- **Hash-chained audit trail** (`app/domain/hash_chain.py`) — every state change appends an entry
  committing to the hash of the one before it. Mutation, deletion, reordering, or splicing an entry
  in from another request all break verification, and `verify_chain()` reports the exact sequence
  number where it broke. Pure, dependency-free, and proven by tests rather than asserted here.
- **Document binding** — the SHA-256 of the exact PDF is captured at request time and re-asserted at
  signing. Signing a different version of the quote is a detectable condition, not an argument.
- **Explicit consent + intent** — both required and recorded, per ESIGN/UETA.
- **Public signing links** — high-entropy `secrets.token_urlsafe(32)` capability tokens, independently
  voidable and expirable without touching the proposal.
- **Evidence bundle** — signer identity, IP, user agent, method, timestamps, consent flags.

## Architecture

```
app/
├── domain/          entities, hash_chain (the core), repository Protocols, events, errors — no I/O
├── application/     use cases over Protocols; unit-testable with no database
├── infrastructure/  session/RLS, ORM models, SQLAlchemy adapters, SECURITY DEFINER resolver
└── interface/       Pydantic DTOs + two routers (authenticated / public)
```

## HTTP surface

Authenticated (gateway supplies `x-tenant-id`):

| Method | Path                                | |
| ------ | ----------------------------------- | --- |
| POST   | `/v1/signature-requests`            | create → returns the signing token |
| GET    | `/v1/signature-requests`            | list (`?proposal_id=`, `?status=`) |
| GET    | `/v1/signature-requests/{id}`       | detail (+ signature once signed) |
| GET    | `/v1/signature-requests/{id}/audit` | the chain + a freshly computed verification |
| POST   | `/v1/signature-requests/{id}/void`  | withdraw a pending request |

Public — **no auth at all** (the signer has no account):

| Method | Path                       | |
| ------ | -------------------------- | --- |
| GET    | `/v1/sign/{token}`         | what am I signing (records `document.opened`) |
| POST   | `/v1/sign/{token}`         | apply signature |
| POST   | `/v1/sign/{token}/decline` | decline |

This is the second public route in the codebase after `/v1/proposals/{id}/view`. It's allowlisted in
the gateway with a narrowly anchored regex, and the response deliberately excludes `tenant_id`,
internal ids, and the audit trail.

## Develop

```bash
uv run --project services/esign-service pytest services/esign-service/tests
```

Runs on port **8007** (`ESIGN_SERVICE_URL` in the gateway config).

## Known limitations (deliberately explicit)

- **A hash chain proves self-consistency, not authenticity.** Anyone with write access to every row
  could mutate an entry and recompute the tail. The database-level mitigation ships in
  `0008_esign.sql` as an append-only trigger (UPDATE/DELETE on `signature_audit_event` raise);
  stronger anchoring (WORM storage, or publishing the head hash externally) is a future step. This
  is asserted by a test named after the limitation so nobody mistakes the guarantee for more than
  it is.
- **No web UI** — tracked as **T204b**. A backend nothing can drive is half a feature; this is the
  same standard applied to T307b.
- **Never run against live Postgres** — the `SECURITY DEFINER` resolver, the RLS policies, and the
  append-only trigger are all Postgres-only and untestable under the SQLite harness. Folded into
  **T311**.
- Single signer only; no countersigning, no certificate-of-completion PDF, and no delivery of the
  link (that's T205 Notifications).
