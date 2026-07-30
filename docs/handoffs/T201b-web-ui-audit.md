# CTO Audit — T201b (AI Quote Assistant web UI)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-07-30
- **Built by:** Agent 2
- **Verdict:** ✅ **Signed off.** All four gate claims reproduced exactly. The two backend fixes this
  task needed are correct and were arrived at by genuinely good reasoning. One correction to the
  report (the work was not actually on `origin`), and one narrowly-scoped security observation from
  the gateway change — neither blocking.

## Gate claims — all four reproduced

| Claim | Result |
| --- | --- |
| Gateway 30/30 | **30 passed** (2 files) |
| Web 84/84 | **84 passed** (9 files) |
| Typecheck clean | clean — both `apps/web` and `apps/api-gateway` |
| Build clean | clean — **15 routes**, including the new `/quotes/new-ai` |

## Correction to the report: it was not on `origin`

The report states T201b was *"merged into main (fast-forward)"*. That is true of the **local** `main`
only — at audit time `git rev-list --left-right --count origin/main...HEAD` returned `0 13`: thirteen
commits ahead, nothing behind. The work was committed and merged locally but had never been pushed,
so nothing was on the remote and no other agent could see it.

Not a defect in the code, and the fast-forward claim itself is accurate. But "merged into main"
reads as *landed*, and it wasn't. Pushed as part of this sign-off.

## What the task actually needed — and got right

T201b is nominally "the web UI", but making voice-to-quote work end to end required two backend
fixes. Both are correct:

### 1. Multipart passthrough in the gateway

`registerServiceProxy` unconditionally did `JSON.stringify(request.body)`, so a `multipart/form-data`
audio upload would have been mangled. The fix forwards a `Buffer` body unchanged and keeps
`JSON.stringify` for everything else — minimal, and the right shape.

Critically, **the identity-header stripping I added in T203/T204 is intact**: `x-tenant-id`,
`x-user-id`, `x-user-roles` are still deleted unconditionally, and `x-forwarded-for` is still
overwritten with the real peer. A body-handling change is exactly where that kind of guard gets
accidentally dropped; it wasn't.

### 2. The 90s AI timeout — opt-in, and for the right reason

`apiFetch`'s fixed 10s timeout is shorter than the AI pipeline's real latency (Whisper + model +
two backend hops). The fix adds an optional per-request `timeoutMs`, **defaults it to the existing
10s for every other caller**, and uses 90s only for the three AI functions. It does not touch
ai-service's own 5s service-to-service timeout, which would have been wrong.

The reasoning in the commit message is worth quoting, because it connects to a gap I flagged in my
own T201 audit: a client-side timeout that fires while the backend keeps running produces a quote
anyway, and **because T201 has no idempotency key**, a manual retry after that false timeout creates
a duplicate draft. That is precisely right, and it's the kind of cross-task reasoning that's easy to
miss.

The same commit also fixed `write-scope-panel.tsx` bypassing the shared `describeAiSubmitError`
mapper, so a 429 spend-cap error surfaced as a bare `Request failed with status 429` — the exact
thing that mapper exists to prevent.

## Finding — non-blocking: the 12 MiB catch-all parser is global

To accept audio uploads, `server.ts` registers a wildcard content-type parser:

```ts
app.addContentTypeParser("*", { parseAs: "buffer", bodyLimit: 12 * 1024 * 1024 }, ...)
```

The `bodyLimit` is well-justified in its comment (Fastify's 1 MiB default would 413 any real
recording at the gateway, before ai-service's own 10 MiB limit is reached). But the parser is
**global**, not scoped to `/v1/ai`.

I probed this rather than assuming, and the result is reassuring on the part that matters:

| Route | 5 MiB `application/octet-stream` POST | Why |
| --- | --- | --- |
| `/v1/quotes` (authenticated) | **401** — rejected before the body is parsed | `onRequest` auth runs before the parsing phase |
| `/v1/sign/{token}` (public) | **500** — body was buffered, reached the proxy | public routes skip auth, so parsing happens |

So the authenticated surface — nearly everything — is unaffected. The exposure is limited to the two
deliberately public routes (`/v1/proposals/{id}/view`, `/v1/sign/*`), which previously would have
415'd a non-JSON body cheaply and now buffer up to 12 MiB first. Rate limiting (100 req/min per IP
for unauthenticated callers) bounds it, but 100 × 12 MiB is real amplification from a single IP.

**Not blocking:** those routes must accept POSTs anyway, the limit is bounded, and rate limiting
applies. **Simple fix when convenient:** scope the parser to the `/v1/ai` prefix, or keep a small
global limit and raise it only where the upload actually lands. Tracked in **T201c**.

## Carried-forward

| Gap | Tracked as |
| --- | --- |
| Global 12 MiB parser should be scoped to `/v1/ai` | **T201c** (new) |
| No idempotency key on `voice-to-quote` — a retry still creates a duplicate draft | M15 spec §6 (the 90s timeout reduces how often this is *reached*, it doesn't fix it) |
| No live-Postgres verification of `ai_usage_log` RLS | **T311b** |
