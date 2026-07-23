# ADR-0001 — Monorepo Structure & Tooling

- **Status:** Accepted (owner: Agent 1)
- **Date:** 2026-07-23
- **Verified:** `pnpm install` (117 pkgs) + `turbo run build --dry` discovers `@tradequote/config` workspace and builds the task graph.

## Context

Four AI agents build web (TS), mobile (Dart), and backend (Python + Node) in parallel. We need
isolation between bounded contexts, shared types, and a fast CI feedback loop without merge chaos.

## Decision

Single monorepo. **pnpm workspaces + Turborepo** for all JS/TS (`apps/web`, `apps/api-gateway`,
`packages/*`). Each Python service (`services/*`) is self-contained with `uv`/Poetry. Flutter app
managed on its own. Shared contracts (types + event registry + OpenAPI) live in `packages/types`
and are the single source of truth Agent 1 governs.

## Consequences

- ✅ One clone, atomic cross-cutting changes, shared CI, enforced "one writer per file" via `TASKS.md`.
- ⚠️ Polyglot tooling — CI must run JS, Python, and Dart lanes. Mitigated by Turborepo remote cache + per-lane GitHub Actions.

## Alternatives considered

Polyrepo (rejected: contract drift, slow cross-changes), Nx (viable; Turborepo chosen for simplicity).
