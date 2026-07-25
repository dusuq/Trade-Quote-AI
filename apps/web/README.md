# Web App (Next.js) — App Shell + Design System (Module M12)

- **Owner Agent:** Agent 2 — Sonnet 5 (this task, T108, built by Agent 1/CTO)
- **Bounded Context / Purpose:** Contractor-facing web application + design system
- **Status:** T108 implemented + verified (19/19 tests, typecheck clean, `next build` produces all
  10 routes as static/prerendered pages with no errors).

## What's here

- **Design system**: Tailwind + a small shadcn/ui-style component set (`Button`, `Input`, `Label`,
  `Card`) in `src/components/ui/`, driven by CSS-variable tokens in `src/app/globals.css` — swap
  the variables for white-label theming, no component changes needed. Dark mode ready (`.dark` class).
- **App shell**: sidebar + top bar (`src/components/app-shell/`) mirroring the core product modules
  (Dashboard, Quotes, Customers, Pricebook, Settings) — see `nav.tsx` for the nav map.
- **Auth flows**: `/login` and `/register`, wired to `services/auth-service` via the API Gateway
  (`src/lib/auth.ts` + `src/lib/api-client.ts`), with Zod-validated forms (react-hook-form) and
  token persistence in `src/lib/auth-store.ts`.
- **Placeholder pages** for Quotes/Customers/Pricebook/Settings so every nav link resolves; each
  names the service it will wire up to next (T109 for quotes, etc.) — see `placeholder-page.tsx`.

## Architecture

```
src/
├── app/
│   ├── (auth)/          login, register — centered layout, no sidebar
│   ├── (app)/            dashboard, quotes, customers, pricebook, settings — sidebar shell
│   ├── layout.tsx        root layout, global providers
│   └── globals.css       design tokens (CSS variables)
├── components/
│   ├── ui/               shadcn-style primitives (Button, Input, Label, Card)
│   └── app-shell/        SidebarNav, AppShell, PlaceholderPage
├── lib/
│   ├── api-client.ts      fetch wrapper -> API Gateway, typed ApiError
│   ├── auth.ts            Zod schemas + login()/register() calls (unit-tested)
│   ├── auth-store.ts      client-side token persistence
│   └── utils.ts           cn() class-merge helper (unit-tested)
└── config.ts              NEXT_PUBLIC_API_URL -> gateway base URL
```

Talks only to the **API Gateway** (`apps/api-gateway`) — never directly to a backend service. The
gateway verifies JWTs and forwards trusted `x-tenant-id`/`x-user-id` headers downstream, per
`docs/07-SERVICE-CONVENTIONS.md`.

## Develop

```bash
pnpm --filter @tradequote/web dev         # http://localhost:3000
pnpm --filter @tradequote/web test        # 19 tests: schemas, cn(), api-client (mocked fetch)
pnpm --filter @tradequote/web build       # next build — compiles + prerenders every route
```

Requires `NEXT_PUBLIC_API_URL` (see `.env.local`, defaults to `http://localhost:8000`).

## Definition of Done

- ✅ Design system with CSS-variable tokens (light/dark, white-label-ready)
- ✅ App shell (sidebar + top bar) matching the product's core modules
- ✅ Auth flows (login/register) wired to auth-service via the gateway, Zod-validated
- ✅ Unit tests on all pure logic (schemas, class-merge, API client incl. error paths) — 19/19
- ✅ `next build` succeeds: all 10 routes compile and prerender with zero type errors
- ⬜ Quote builder UI, Customer/Pricebook data wiring — T109 and beyond
- ⬜ Component-level (Testing Library) tests — not yet added; pure-logic coverage only for T108
