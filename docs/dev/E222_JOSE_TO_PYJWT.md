# #222 — Migrate JWT auth from python-jose to PyJWT

**Status:** DONE · **Scope:** auth library swap + CVE-ignore cleanup · **Date:** 2026-06-05

## Why

`python-jose` carried the last two `pip-audit` ignores we could not actionably
fix while we depended on it:

- **PYSEC-2025-185** — jose JWE-bomb DoS (no upstream fix).
- **CVE-2026-30922** — pyasn1 BER-decoder recursion DoS; the real fix (pyasn1
  0.6.3) was blocked by jose's `pyasn1<0.5.0` cap.

Both were *not reachable* in our code (we mint/verify HS256 JWS only — never JWE,
never an ASN.1/asymmetric path), so they were justified ignores. But "ignored,
not-reachable" is weaker than "gone". `PyJWT` is the maintained, mainstream JWT
library; on HS256 it needs **no crypto extra** (HMAC is stdlib), so the swap
deletes the entire `jose` / `ecdsa` / `pyasn1` / `rsa` chain that carried both
CVEs. Net: the audited dependency set no longer contains either vulnerability —
no reachability caveat required.

## Exit criteria (all met)

1. `python-jose` removed from `requirements.txt`; `PyJWT==2.13.0` pinned. ✅
2. JWT mint/verify behaviour unchanged: same claims, same HS256 algorithm, same
   expiry semantics, same rejection of invalid/expired/tampered tokens. ✅
3. The two jose/pyasn1 CVE ignores removed from CI; `pip-audit` is clean with
   only the dev-only pytest ignore (`CVE-2025-71176`, tracked by #221). ✅
4. No app module imports `jose` (regression-guarded by a test). ✅
5. Full suite green; contracts 14/14; drift OK. ✅

## What changed (typed contract preserved)

The public contract of `app/auth/jwt.py` — `create_access_token(...) -> Token`
and `decode_token(str) -> TokenData` — is **unchanged**. The only contract
change is the *failure* type, and it was deliberately made cleaner:

- **New app-level exception `TokenError`** (`app/auth/jwt.py`). `decode_token`
  now raises `TokenError` on any decode/validation failure (it wraps PyJWT's
  `jwt.PyJWTError`, which covers `ExpiredSignatureError`, signature failures,
  malformed tokens). Callers used to `from jose import JWTError` directly — a
  vendor-SDK leak across three files. They now catch `app.auth.jwt.TokenError`,
  so **this module is the only place that knows which JWT library we use**; a
  future swap stays a one-file change (provider/adapter rule).

| File | Change |
|---|---|
| `requirements.txt` | `python-jose[cryptography]==3.4.0` → `PyJWT==2.13.0` |
| `app/auth/jwt.py` | `import jwt`; add `TokenError`; `decode_token` wraps `jwt.PyJWTError` → `TokenError` |
| `app/auth/dependencies.py` | catch `TokenError` instead of `JWTError` (2 sites) |
| `app/api/middleware.py` | catch `TokenError` instead of `JWTError` (1 site) |
| `.github/workflows/ci.yml` | drop `PYSEC-2025-185` + `CVE-2026-30922` ignores; keep only pytest |
| `CHANGELOG.md` | Security entry |
| `tests/test_jwt_pyjwt_migration.py` | NEW — round-trip + every failure mode → `TokenError` + no-jose-import guard |

## Tests

`tests/test_jwt_pyjwt_migration.py` (8, infra-free): round-trip claim fidelity;
garbage / tampered-signature / expired / missing-field / invalid-role /
wrong-secret all raise `TokenError`; and a regression guard asserting none of the
three auth modules reference `jose`. Existing `test_auth_hardening.py` (13) +
`test_tenant_isolation_rls.py` exercise the real `get_current_user` end to end
and remain green — proving the caller-side `TokenError` catch wired correctly.

## Verification

- `pip-audit -r requirements.txt --ignore-vuln CVE-2025-71176` → **No known
  vulnerabilities found** (jose + pyasn1 CVEs gone). dev requirements likewise.
- Round-trip + invalid/tampered/expired smoke passed against real `settings`.
- Full suite **305 passed, 3 skipped**; contracts 14/14; drift OK.
- `pip check` → no broken requirements after removing jose/ecdsa/rsa.

## Notes

- We only use **HS256** (`settings.jwt_algorithm`), so plain `PyJWT` (no
  `[crypto]` extra) is sufficient and keeps the image slim. If the platform ever
  needs RS/ES asymmetric signing, add `PyJWT[crypto]` (pulls `cryptography`) —
  but that is a deliberate, separate decision, not a silent default.
- PyJWT verifies `exp` by default and returns `str` from `encode` (2.x), so no
  call-site changes were needed beyond the import and exception type.
