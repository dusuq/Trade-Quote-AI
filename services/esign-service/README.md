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

| Method | Path                                |                                             |
| ------ | ----------------------------------- | ------------------------------------------- |
| POST   | `/v1/signature-requests`            | create → returns the signing token          |
| GET    | `/v1/signature-requests`            | list (`?proposal_id=`, `?status=`)          |
| GET    | `/v1/signature-requests/{id}`       | detail (+ signature once signed)            |
| GET    | `/v1/signature-requests/{id}/audit` | the chain + a freshly computed verification |
| POST   | `/v1/signature-requests/{id}/void`  | withdraw a pending request                  |

Public — **no auth at all** (the signer has no account):

| Method | Path                       |                                               |
| ------ | -------------------------- | --------------------------------------------- |
| GET    | `/v1/sign/{token}`         | what am I signing (records `document.opened`) |
| POST   | `/v1/sign/{token}`         | apply signature                               |
| POST   | `/v1/sign/{token}/decline` | decline                                       |

This is the second public route in the codebase after `/v1/proposals/{id}/view`. It's allowlisted in
the gateway with a narrowly anchored regex, and the response deliberately excludes `tenant_id`,
internal ids, and the audit trail.

## Develop

```bash
uv run --project services/esign-service pytest services/esign-service/tests
```

Runs on port **8007** (`ESIGN_SERVICE_URL` in the gateway config).

### Upstream dependency (T204c)

Creating a signature request synchronously reads `GET /v1/proposals/{id}` from **proposal-service**
(`PROPOSAL_SERVICE_URL`, default `http://localhost:8005`) to confirm the proposal exists in the
caller's tenant and is actually sendable. [ADR-0003](../../docs/adr/ADR-0003-sync-service-to-service-http.md)
permits this because the call is _part of fulfilling the request_ — if it fails, creating the
request isn't meaningfully complete, since we'd be opening a legal audit trail against a document
we never confirmed exists.

Three consequences worth knowing:

- **It fails closed.** proposal-service unreachable → `502`, and nothing is written.
- **The call happens before any transaction opens** (ADR-0003 rule 3). `test_proposal_is_read_
before_any_transaction_opens` pins the ordering rather than just asserting empty tables — a
  rollback would leave those empty too.
- **Cross-tenant protection is proposal-service's RLS**, reached by forwarding the caller's
  `x-tenant-id`. Another tenant's proposal comes back `404`, indistinguishable from one that
  doesn't exist — so this service can't be used to probe for it.

Statuses: `sent` and `viewed` are signable; `draft` is rejected with `409`, because a draft's public
`/view` 404s by design and the signer could never open the document.

## Known limitations (deliberately explicit)

- **A hash chain proves self-consistency, not authenticity.** Anyone with write access to every row
  could mutate an entry and recompute the tail. The database-level mitigation ships in
  `0008_esign.sql` as an append-only trigger (UPDATE/DELETE on `signature_audit_event` raise);
  stronger anchoring (WORM storage, or publishing the head hash externally) is a future step. This
  is asserted by a test named after the limitation so nobody mistakes the guarantee for more than
  it is.
- ~~**No web UI**~~ — shipped in **T204b** (contractor request/tracking + the public `/sign/[token]`
  page), CTO-audited and signed off.
- **`document_sha256` is still the client's word.** T204c validates that the _proposal_ exists and
  is sendable, but the hash the request is created against is computed by the contractor's browser
  — this service never fetches the PDF to verify it. That's a deliberate cost trade-off, and it
  doesn't weaken what the chain proves: the signature is bound to whatever hash was recorded, and a
  signer whose document doesn't match that hash is rejected. It does mean "the document on record"
  means "the document the contractor's browser saw", not "the document proposal-service holds".
- **Never run against live Postgres** — the `SECURITY DEFINER` resolver, the RLS policies, and the
  append-only trigger are all Postgres-only and untestable under the SQLite harness. Folded into
  **T311**.
- Single signer only; no countersigning, no certificate-of-completion PDF, and no delivery of the
  link (that's T205 Notifications).
