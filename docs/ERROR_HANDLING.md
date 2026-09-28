# Error Handling and Error Boundaries

How failures are caught, shaped, and shown, from the database up to the screen. Rule of thumb:
**a user only ever sees a message written for them.** Raw exceptions, stack traces, and bare
status text never reach the UI (CLAUDE.md §17).

## 1. Backend: one error envelope

Every response, success or failure, uses the same envelope:

```json
{ "data": null, "error": { "code": "validation_error", "message": "One or more fields are invalid.",
  "field_errors": { "amount_minor": "Input should be greater than 0" } }, "meta": null }
```

Handlers are registered in `backend/app/core/errors.py::register_exception_handlers`:

| Source | HTTP | `code` | Message shown |
|---|---|---|---|
| `ValidationAppError` (service-level rule, e.g. transfer to the same account) | 422 | `validation_error` | Specific, e.g. "Choose a different destination account.", plus `field_errors` |
| FastAPI `RequestValidationError` (schema, type, or bounds failure) | 422 | `validation_error` | "One or more fields are invalid.", with per-field `field_errors` (dotted paths, `body` stripped) |
| `AuthenticationError` (missing or expired token, bad CSRF) | 401 | `unauthenticated` | e.g. "Invalid or expired session. Please log in again." |
| `AuthorizationError` | 403 | `forbidden` | Specific |
| `NotFoundError` (including another user's resource; see below) | 404 | `not_found` | e.g. "Transaction not found." |
| `ConflictError` (e.g. a second budget for the same category) | 409 | `conflict` | e.g. "A budget for this category already exists. Edit it instead." |
| slowapi `RateLimitExceeded` | 429 | `rate_limited` | "Too many requests. Please try again shortly." |
| Starlette `HTTPException` (unknown route, wrong method) | its own status | `not_found` / `http_error` | The exception's `detail` string |
| **Any other exception** | 500 | `internal_error` | "Something went wrong on our end. Please try again." The full traceback is logged server-side with `logger.exception` (method and path) and never sent to the client. |

Design points:

- **Validation happens at the boundary and again in the service.** Pydantic enforces types and
  bounds, for example `amount_minor > 0` and the length limits. Services enforce cross-field and
  ownership rules. Database CHECK/UNIQUE constraints are the last line of defense.
- **Cross-user access is reported as 404.** Repositories filter by `(id, user_id)`, so another
  user's resource is simply "not found", and the response doesn't confirm it exists.
- **Constraint races become normal responses, not 500s.** `transaction_service.create_transaction`
  catches the `IntegrityError` from a concurrent duplicate `Idempotency-Key` or recurring
  occurrence, rolls back, and returns the row that won the race.
- **Unconfigured integrations don't fail silently.** AI, OCR, storage, and sync fall back to
  labeled mock providers. Missing *required* settings (DB URL, JWT secret of 32+ characters,
  and so on) fail at startup (`app/core/config.py`).

Tests: `test_auth.py` (401 paths), `test_rate_limiting.py` (real 429 responses on the limited
routes; the `rate_limited` code in the envelope isn't asserted), every
`test_<entity>.py` (422 field errors, 404 for cross-user access, 409 conflicts),
`test_security_headers.py`.

## 2. Frontend: three layers

### Layer 1: the API client (`frontend/lib/api-client.ts`)

- A well-formed backend error envelope becomes an `ApiError` with `status`, `code`, `message`,
  and `fieldErrors`. Its `message` was written by the backend for users, so it's safe to display.
- Anything else rejects with a plain `Error`: a network failure (`fetch` throws), a non-JSON body
  such as a proxy's HTML 502, or a blob download failure without an envelope. Callers never
  display that error's text.

### Layer 2: inline error, loading, and empty states (every data view)

Every page under `app/(app)/` follows the same pattern:

```tsx
try { setData(await listThings(accessToken)); }
catch (err) { if (isMounted) setError(err instanceof ApiError ? err.message : "Failed to load things."); }
```

- **Error:** a red inline panel next to the content, with a **Try again** button that bumps a
  `reloadToken` to refetch. The rest of the page and the navigation stay usable.
- **Loading:** `components/ui/skeleton.tsx` placeholders shaped like the real content (used in 21
  files), not blank flashes or spinners.
- **Empty:** a dashed-border panel explaining what to do next, e.g. "Add your first account…",
  never a bare "No data".
- **Forms** (the account, budget, category, goal, receipt-review, recurring, subscription, and
  transaction forms, plus the register page) map `ApiError.fieldErrors` onto the matching inputs, show `ApiError.message` through
  `components/ui/form-error.tsx` (`role="alert"`) when there are no field errors, and fall back to
  "Something went wrong. Please try again." for anything else.
- **Offline writes:** the add-expense sheet queues to IndexedDB when offline, and the header's
  `SyncStatusIndicator` shows pending or failed sync. A 401 during replay is handled in
  `lib/offline/sync-queue.ts`.

### Layer 3: route-level error boundaries (render-time exceptions)

Layer 2 only catches failed requests. If a component **throws while rendering** (for example a
chart given an unexpected payload shape), React unmounts the tree up to the nearest error
boundary. These boundaries use the Next.js App Router `error.js` convention:

| File | Catches | Behavior |
|---|---|---|
| `app/(app)/error.tsx` | Any signed-in page | Renders **inside** `(app)/layout.tsx`, so the sidebar and bottom nav survive and the user can navigate away. "Try again" calls `retry()`; there's a link to the dashboard. |
| `app/error.tsx` | Public pages (landing, login, register, offline) | Same fallback, with a link to `/`. |
| `app/global-error.tsx` | Exceptions in the root layout itself (`AuthProvider`, `ThemeSync`, SW registration) | Replaces the root layout, renders its own `<html>`/`<body>`, and imports `globals.css`. |
| `app/not-found.tsx` | Unknown routes / `notFound()` | Themed 404 with links to the dashboard and home. |

All three error boundaries render `components/ui/error-fallback.tsx`, which:

- never renders `error.message`, only fixed, friendly copy;
- is a `role="alert"` region, so screen readers announce it;
- shows `error.digest` as a "Reference" when Next.js provides one (server-component errors), so
  a user can quote it and it can be matched against server logs;
- logs the error with `console.error` in a `useEffect`. There's no remote error-reporting service
  configured.

Tests: `frontend/tests/error-boundaries.test.tsx` checks that each boundary renders an alert,
never shows the raw error message, calls `retry` on "Try again", logs the error, and links to a
safe page. It also covers the 404 page. `global-error.tsx` isn't rendered under test because it
emits its own `<html>` element. It shares the tested `ErrorFallback` component.

## 3. Known gaps

These are recorded as found in the code. They haven't been fixed as part of this documentation
pass.

- **Access-token expiry mid-session.** Access tokens last `ACCESS_TOKEN_EXPIRE_MINUTES` (15 in
  `.env.example`). Nothing refreshes them proactively, and only the offline sync queue handles a
  401. After expiry, pages show the backend's "Invalid or expired session. Please log in again."
  inline until the user reloads, which restores the session through the refresh cookie. A safe
  fix needs single-flight refresh, because refresh tokens rotate and reuse is treated as
  compromise (`session.reuse_detected`).
- **Inline page error panels aren't live regions.** Form errors use `role="alert"`, but most
  page-level red panels are plain `<div>`s, so screen readers don't announce them automatically.
- **Server-side error logs** include method, path, and traceback, but no request ID or user ID
  (CLAUDE.md §17 asks for both).
- **No remote error reporting** (Sentry or similar) for client-side exceptions. Boundaries log to
  the browser console only.
