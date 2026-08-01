# Web App (Next.js) — App Shell + Design System + Quote Builder (Modules M12)

- **Owner Agent:** Agent 2 — Sonnet 5 (T108/T109 built by Agent 1/CTO)
- **Bounded Context / Purpose:** Contractor-facing web application + design system
- **Status:** T108 + T109 implemented + verified (45/45 tests, typecheck clean, `next build`
  produces all 11 routes with zero errors; quote builder/list/detail pages live-verified in-browser
  against both mocked-success and real-gateway-unreachable conditions).

## What's here

- **Design system**: Tailwind + a small shadcn/ui-style component set (`Button`, `Input`, `Label`,
  `Card`, `Badge`, `Select`) in `src/components/ui/`, driven by CSS-variable tokens in
  `src/app/globals.css` — swap the variables for white-label theming, no component changes needed.
- **App shell**: sidebar + top bar (`src/components/app-shell/`) mirroring the core product modules
  (Dashboard, Quotes, Customers, Pricebook, Settings), gated by `useAuthGuard()` — unauthenticated
  users are redirected to `/login` before any protected page renders.
- **Auth flows**: `/login` and `/register`, wired to `services/auth-service` via the API Gateway.
- **Quote builder (T109)**: `/quotes` (list, live data), `/quotes/new` (full builder: customer
  picker from customer-service, dynamic line items via `useFieldArray`, live subtotal preview,
  Zod-validated), `/quotes/[id]` (detail: line items, totals, status-conditional Send/Accept/Reject
  actions) — all wired to `services/quote-service` via the gateway.
- **Placeholder pages** remaining for Customers/Pricebook/Settings — each names the service it
  wires up to next.

## Architecture

```
src/
├── app/
│   ├── (auth)/          login, register — centered layout, no sidebar
│   ├── (app)/            dashboard, quotes (+new, +[id]), customers, pricebook, settings
│   ├── layout.tsx        root layout, global providers
│   └── globals.css       design tokens (CSS variables)
├── components/
│   ├── ui/               shadcn-style primitives (Button, Input, Label, Card, Badge, Select)
│   └── app-shell/        SidebarNav, AppShell, PlaceholderPage
├── lib/
│   ├── api-client.ts      fetch wrapper -> API Gateway; hard 10s timeout + typed ApiError so a
│   │                       page's loading state can never hang forever on an unreachable backend
│   ├── auth.ts            Zod schemas + login()/register() calls (unit-tested)
│   ├── auth-store.ts      client-side token persistence
│   ├── use-auth-guard.ts  redirects to /login when no token; gates the (app) route group
│   ├── customers.ts       listCustomers() for the quote builder's customer picker
│   ├── quotes.ts          Zod form schemas, dollars<->minor-unit mapping, quote-service client
│   │                       (list/get/create/addLineItem/send/accept/reject), all unit-tested
│   ├── money.ts           formatMoney()/parseMoneyToMinor() — mirrors the Python Money convention
│   └── utils.ts           cn() class-merge helper (unit-tested)
└── config.ts              NEXT_PUBLIC_API_URL -> gateway base URL
```

Talks only to the **API Gateway** (`apps/api-gateway`) — never directly to a backend service. The
gateway verifies JWTs and forwards trusted `x-tenant-id`/`x-user-id` headers downstream, per
`docs/07-SERVICE-CONVENTIONS.md`.

## Develop

```bash
pnpm --filter @tradequote/web dev         # http://localhost:3000
pnpm --filter @tradequote/web test        # 129 tests: pure logic + component behaviour
pnpm --filter @tradequote/web build       # next build — compiles + prerenders every route
```

Requires `NEXT_PUBLIC_API_URL` (see `.env.local`, defaults to `http://localhost:8000`).

### Writing tests

Two kinds, and **the distinction is load-bearing** (T204d):

| | file | environment |
| --- | --- | --- |
| Pure logic — schemas, money math, error mappers, API clients | `*.test.ts` | `node` (the global default) |
| Component behaviour — focus, disabled states, what a click actually does | `*.test.tsx` | `jsdom`, **opted into per file** |

A `.tsx` test **must** start with this docblock, or it fails with `document is not
defined`:

```tsx
// @vitest-environment jsdom
```

The global environment stays `node` deliberately: most tests here need no DOM, and
paying for one everywhere is slower for no benefit. `vitest.config.ts` sets
`esbuild.jsx: "automatic"` because Next compiles JSX itself (`tsconfig` uses
`jsx: "preserve"`), so vitest has to be told which runtime to use.

Component tests use `@testing-library/react`. Note there is **no `@testing-library/jest-dom`**,
so matchers like `toBeDisabled()` are unavailable — assert on the DOM property
instead:

```tsx
expect((button as HTMLButtonElement).disabled).toBe(true);
```

Prefer queries that assert what a user can actually reach — `getByRole`,
`getByLabelText` — over test ids. `copilot-panel.test.tsx` and `dialog.test.tsx` are the
worked examples.

## Definition of Done

- ✅ Design system with CSS-variable tokens (light/dark, white-label-ready)
- ✅ App shell (sidebar + top bar), auth-guarded, matching the product's core modules
- ✅ Auth flows (login/register) wired to auth-service via the gateway, Zod-validated
- ✅ Quote builder (T109): customer picker, dynamic line items, live subtotal, create/list/detail/
  send/accept/reject, all wired to quote-service via the gateway
- ✅ Unit tests on all pure logic — 45/45 (schemas, class-merge, money math, API client incl.
  network-failure/timeout paths, dollars→minor-units quote-payload mapping)
- ✅ `next build` succeeds: all 11 routes compile with zero type errors
- ✅ **Live-verified in-browser** (not just built): quote builder's dynamic line items, live
  subtotal calc, and Zod validation confirmed working via real interaction; list/detail pages
  confirmed rendering correctly against a mocked real API response (correct money formatting,
  status badges, status-conditional actions, null-title handling)
- ✅ **Gap closed under T206:** the "couldn't load" error banner was previously unconfirmed against a
  completely unreachable gateway (see history below). It has now been verified in a real browser: with
  the Next dev server on `:3000` and no backend running, both `GET /v1/quotes/summary` and
  `GET /v1/quotes?limit=5` returned `ERR_CONNECTION_REFUSED`, and both error banners rendered visibly
  with no unhandled console rejections — confirming the `isError` logic and fetch/error-wrapping code
  work correctly outside the sandbox.
  <details>
  <summary>Original gap description (historical)</summary>

  When the gateway is completely unreachable, the "couldn't load" error banner did not render in one
  specific sandboxed/automated-browser test session, despite the underlying `isError` logic and the
  fetch/error-wrapping code being correct per unit tests and code review. Root cause narrowed to
  react-query's internal `fetchStatus` handling in that environment (ruled out: `networkMode`
  heuristic, React Strict Mode double-invoke — neither fixed it). Mitigated defensively with a hard
  request timeout (`AbortSignal.timeout`, 10s) and proper `ApiError` wrapping for network failures
  either way.
  </details>
- ✅ **Component-level (Testing Library) tests — added under T204d.** jsdom +
  `@testing-library/react`, opted into per file (see [Writing tests](#writing-tests)). Covers the
  `Dialog` focus trap and the copilot panel's write actions. Both suites were **mutation-tested** —
  reverting the behaviour under test makes them fail — and the dialog suite immediately caught a
  real defect that typecheck and `next build` could not see: focus landed on the close button, so a
  keyboard user's first Enter dismissed the dialog.
- ⬜ Customer/Pricebook data wiring — still beyond T109's scope
