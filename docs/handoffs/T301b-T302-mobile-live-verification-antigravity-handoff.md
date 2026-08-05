# 🔀 Handoff — T301b / T302 (M13/M14 Mobile): on-device offline↔online sync verification

- **From:** Agent (Claude Code, Sonnet 5)
- **To:** **Agent 3 — Google Antigravity (Gemini)**
- **Assigned:** 2026-08-03
- **How to use this file:** paste this whole document as the first message into your next
  Google Antigravity session.

---

## Why you're getting this

T301b and T302 are already `DONE` and CTO-signed-off (`TASKS.md` rows, re-audited 2026-08-02) —
`flutter analyze`/`flutter test` were re-run and passed. Their sign-off explicitly named two
follow-ups as "not blocking, but verify before calling this truly done":

1. An on-device (or emulator) offline→online sync cycle against a **live backend** — static
   review and unit tests can't exercise real connectivity transitions, a real SQLite file, or a
   real gateway round-trip.
2. Secure token persistence — the access token lived in-memory only, so an app restart would
   strand a logged-in contractor and any queued offline mutations behind the login screen.

**Item 2 is done** (see below) and machine-verified via `flutter test`. **Item 1 needs a real
device/emulator + a running backend**, and — same constraint as
[T204b](T204b-live-verification-antigravity-handoff.md#why-youre-getting-this),
[T202b](T202b-live-verification-antigravity-handoff.md), and
[T307b/T311](T307b-T311-antigravity-handoff.md) before it — this machine has no reachable Docker
daemon (`docker ps` fails to connect; Docker Desktop was launched and polled for ~4 minutes
without the daemon coming up) and no Android emulator image (`flutter emulators` finds none;
only Windows-desktop and Chrome/Edge web Flutter targets are available locally). You're already
set up to spin up a disposable environment for this.

## What's already done (no action needed on these)

- **`flutter analyze`: no issues found.** **`flutter test`: 40/40 pass** — the pre-existing 12
  (currency/bps/quote-calc + conflict-resolver) plus 28 new tests added this pass:
  - `test/api_client_test.dart` — header construction (Bearer token present/absent), GET/POST
    success paths, 4xx/5xx error paths, network-failure wrapping.
  - `test/sync_queue_test.dart` — enqueue/FIFO ordering, retry-ceiling exclusion, markFailed
    increments retry_count, markCompleted deletes the row, removeForEntity, pendingCount —
    against a real in-memory SQLite DB (`sqflite_common_ffi`), not a mock.
  - `test/sync_engine_test.dart` — `pushPendingMutations` success/failure/verb-per-action;
    `pullCustomers`/`pullQuotes` conflict resolution against a real in-memory DB + a mocked HTTP
    client; the `syncAll` re-entrancy guard.
  - `test/auth_state_test.dart` — JWT-claims decoding into `UserSession`, persistence on login,
    no persistence on a failed login, `logout()` clearing storage, `restoreSession()` rehydration.
  - **A real bug was caught and fixed by the new `sync_engine_test.dart` coverage**: the wire
    payload for customers uses `display_name`, but the local SQLite schema's column is `name`.
    `ConflictResolver.resolveScalar` merges by exact key name, so a newer local rename to `name`
    could never win — the server's `display_name` key rode through untouched and
    `LocalDatabase.upsertCustomer`'s `display_name ?? name` fallback silently kept the stale
    server value, defeating last-write-wins for customer renames specifically (quotes didn't
    have this bug — their wire/local field names already match). Fixed in
    `lib/core/sync/sync_engine.dart`'s `pullCustomers` by aliasing `display_name` → `name` before
    conflict resolution.
- **Secure token persistence implemented:**
  - Added `flutter_secure_storage` (pubspec.yaml) and a new `lib/core/storage/token_store.dart`
    (`TokenStore` interface + `SecureTokenStore` impl) so `AuthNotifier` is testable via an
    injectable fake in unit tests while using real OS-backed secure storage
    (Keychain/Keystore/DPAPI) in production.
  - `lib/features/auth/domain/auth_state.dart`: `login()` now persists the full session
    (tokens + claims) to secure storage; `logout()` clears it; a new `restoreSession()` rehydrates
    state from storage.
  - `lib/main.dart`: `main()` is now `async`, builds a `ProviderContainer`, calls
    `container.read(authProvider.notifier).restoreSession()` **before** `runApp`, then runs the
    app via `UncontrolledProviderScope` — so a cold restart lands an already-authenticated
    contractor straight past the login screen with their sync queue intact, instead of losing
    the session.
  - `ApiClient` and `SyncEngine` were also refactored to accept an injectable `http.Client`
    (defaults to a real `http.Client()`), which is what made the new tests possible without
    hitting the network.

## What's needed from you

1. Bring up the dev stack (`pnpm dev:up` for Docker services — Postgres + auth-service +
   customer-service + the gateway — then whatever's needed for `apps/api-gateway`), or your
   disposable-VM equivalent.
2. Get an Android emulator (or physical device) running — `apps/mobile`'s default gateway base
   URL is `http://10.0.2.2:8000`, the standard Android-emulator alias for the host loopback, so
   an Android target is the path of least friction. (If you instead use the Windows-desktop or
   web Flutter target, you'll need to point the app at `http://localhost:8000` — the base URL is
   currently a hardcoded constant in `api_client.dart` / `auth_state.dart` / `sync_bootstrap.dart`,
   not an env override, so you'd have to edit those locally for that target and revert before
   committing.)
3. `cd apps/mobile && flutter run` targeting the emulator/device.
4. Run through the actual gaps this handoff exists for:
   1. **Login** with a seeded tenant/contractor (check `services/auth-service` or a seed script
      for credentials — `login_screen.dart` defaults to `apex-trades` /
      `contractor@apex-trades.com` as placeholder text, but the password and whether that tenant
      exists depend on your seed data). Confirm it navigates to `/customers` with live data, not
      mock data.
   2. **Secure persistence check (the actual point of this handoff item):** fully kill the app
      process (not just background it — e.g. remove it from recents / `flutter run` stop and
      relaunch, or force-stop via `adb shell am force-stop`), then relaunch. Confirm it lands
      directly on `/customers` (already authenticated), not `/login`.
   3. **Offline edit → queue:** put the emulator in airplane mode (or otherwise cut network),
      edit a customer or a quote. Confirm the offline banner's pending-sync-count badge
      increments and the app remains fully usable offline (reads from local SQLite).
   4. **Reconnect → replay:** restore connectivity. Confirm `SyncBootstrap`'s periodic sync (every
      5 min) or a manual trigger replays the queued mutation against the live gateway, the
      pending count drops back to 0, and the edit is now visible from a second client (e.g. the
      web app or a direct API call) hitting the same tenant.
   5. **Conflict resolution, live:** with the app offline, edit a quote's title locally. While
      still offline, change the _same_ quote's title via another client (web app or direct API
      call) so the server's `updated_at` differs from what the device will eventually see.
      Reconnect and let sync run. Confirm: the more-recently-`updated_at`-stamped edit wins for
      `title`, but server-authoritative money fields (`tax_rate_bps`, `total_minor`, `tax_minor`,
      `unit_cost_minor`, `subtotal_minor`, `default_markup_bps`) always reflect the server's
      values regardless of which side was newer — this is the invariant `conflict_resolver_test.dart`
      and the new `sync_engine_test.dart` pin at the unit level; this step is what actually proves
      it end-to-end.
5. Report results the same way T002b/T311/T204b did: paste what you saw (or screenshots/adb
   logs) into a Results section here, tear down anything you spun up, and update the "Mobile
   live-verify" follow-up note in `TASKS.md` + `tracking/PROGRESS-TRACKER.csv` once confirmed —
   T301b/T302 are already `DONE`; this closes the named follow-up rather than re-flipping their
   status.

## Standing rules (same as always)

- If you find a bug, prefer reporting it precisely (file, line, repro steps) over silently
  patching around it, unless it's a one-line fix — in which case flag clearly in your commit
  message what you touched and why.
- Re-run `flutter analyze && flutter test` inside `apps/mobile` if you touch any Dart source
  before/after your live pass.
