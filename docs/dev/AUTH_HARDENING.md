# Auth Hardening (E2) — Reviewer Note

_Last updated: 2026-05-31. Companion to `docs/dev/TENANT_ISOLATION.md` (E1)._

This note is for a security reviewer evaluating how the platform authenticates
users and manages credentials. It states what was broken, what changed, and the
properties the change now guarantees — with the test that proves each one.

## Threat model addressed

A signed JWT is, by itself, **bearer + irrevocable until `exp`**. Combined with
the bugs found below, that meant: a stolen/old token could not be killed, the
same email could not be reasoned about consistently, cookies were not
HTTPS-only off the dev box, and invites handed out plaintext passwords. E2
closes these.

## What was wrong (verified against the code, 2026-05-30)

| # | Finding | Evidence |
|---|---------|----------|
| 1 | Cookie `secure=False` hardcoded — sent over plain HTTP in prod | `auth_routes.py:31` (old) |
| 2 | Schema says `UNIQUE(email)` (global) but code used `ON CONFLICT (email, org_id)` (per-org) — multi-org signup silently broke | `schema.sql:418` vs `auth_routes.py:207` (old) |
| 3 | No way to revoke a JWT before expiry (logout cleared only the cookie; a copied token kept working) | no session/denylist table |
| 4 | Invite returned a **plaintext temporary password** in the HTTP response | `auth_routes.py:281,307` (old) |
| 5 | No password-reset flow at all | — |

## What changed

### 1. Email model — one account per email (chosen deliberately)
Email is unique **platform-wide** (`UNIQUE(email)` kept). Code now agrees:
duplicate signup → **409**; `_ensure_dev_user` uses `ON CONFLICT (email)`. Login
keys on email alone and is therefore unambiguous. (Multi-org membership for one
human is a future feature, not a launch blocker — see BACKLOG.)

### 2. Secure cookies are environment-aware
`settings.cookie_secure` defaults to **True** when `ENVIRONMENT` is
`production`/`staging`, False in dev; override with `COOKIE_SECURE`. The cookie
remains `HttpOnly` + `SameSite=Lax`.

### 3. Server-side revocation — session allowlist (`auth_sessions`)
Every issued token now carries a unique **`jti`**. At issue time a row is written
to `auth_sessions` (jti, user_id, org_id, expires_at, revoked_at). `get_current_user`
checks the row is **present, not revoked, not expired** on every request
(`app/auth/sessions.py::session_is_active`). This makes a JWT genuinely
revocable:
- **logout** → revoke this jti (`revoke_session`);
- **password reset / departure / breach** → revoke ALL of a user's sessions
  (`revoke_user_sessions`).

A validly-signed token that was never registered (e.g. minted out-of-band) is
rejected — the allowlist is authoritative. Legacy tokens with no `jti` are
allowed through (backward compat) and age out at `exp`.

**Cost / placement.** The check is one indexed lookup per authenticated request
on the **owner (RLS-exempt) engine** — the same identity path that already reads
`users` for `/me`. It **fails closed**: if the lookup errors it returns False
(→ 401), so an unverifiable session never authorises. This is the deliberate
trade for real revocability ("JWT alone can't be revoked").

**SSE endpoint.** `/api/v1/evaluate/{run_id}/stream` authenticates cookie-only
(EventSource cannot set an `Authorization` header) and so does **not** go through
the `get_current_user` dependency. It calls the same `_token_not_revoked` check
explicitly after decoding — otherwise a logged-out/revoked token could keep
streaming until `exp`. The only other direct `decode_token` use is
`OrgContextMiddleware`, which merely derives the (immutable, signed) `org_id` to
set the RLS context — every such request is still gated by `get_current_user` in
its handler.

### 4. Invites & password reset — one-time, expiring, hash-at-rest (`auth_onetime_tokens`)
`app/auth/tokens.py`:
- High-entropy `secrets.token_urlsafe(32)`; only the **SHA-256 hash** is stored.
- `consume_token` spends the token atomically (`UPDATE … RETURNING`), so it is
  single-use even under a race; expired/used/wrong-purpose tokens return None.
- **Invite**: admin gets an invite *token* (link), never a password. Invitee
  redeems it at `/invite/accept` and sets their own password.
- **Reset**: `/password-reset/request` is generic-202 (no account enumeration)
  and, in prod, emails a short-lived (1h) token; `/password-reset/confirm`
  sets the new password and revokes all existing sessions.

**No endpoint returns a plaintext or temporary password.**

### 5. Minimum password length
8 chars, enforced on signup / invite-accept / reset-confirm (`_validate_password`).

## Storage

`auth_sessions` and `auth_onetime_tokens` are RLS-enabled, `FORCE`d, and granted
to `platform_app` (mirrors E1). They are accessed via the owner engine on the
identity path; RLS is defence-in-depth. `schema.sql` + Alembic `0012`.

## Exit criteria → test

| Criterion | Test in `tests/test_auth_hardening.py` |
|-----------|----------------------------------------|
| prod secure cookies | `test_cookie_secure_follows_environment` |
| email uniqueness consistent | `test_duplicate_email_signup_is_409` |
| revoked tokens rejected | `test_logout_revokes_session`, `test_minted_token_without_session_is_rejected` |
| no plaintext passwords; invite = one-time token | `test_invite_returns_token_not_password` |
| invite single-use | `test_invite_accept_is_single_use` |
| reset = expiring one-time token; revokes sessions | `test_password_reset_flow_revokes_sessions` |
| no account enumeration | `test_password_reset_request_does_not_enumerate` |
| abuse: weak pw / bad tokens / wrong role | `test_weak_password_rejected`, `test_invite_accept_bad_token_rejected`, `test_password_reset_confirm_bad_token_rejected`, `test_invite_requires_privileged_role` |

## Known follow-ups (tracked in BACKLOG)

- `auth_sessions` housekeeping (`purge_expired_sessions`) is implemented but not
  yet scheduled — wire into the existing cleanup cron.
- Wire real email delivery for invite/reset links (Phase 8 SMTP channel exists).
- Rate-limit `/token` and `/password-reset/request` (brute-force / abuse).
- Optional: rotate `jti` on token refresh once a refresh-token flow exists.
