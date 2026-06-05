# #221 — Bump pytest 8 → 9 (clear the final CVE ignore)

**Status:** DONE · **Scope:** dev/test dependency bump + zero-ignore CVE gate · **Date:** 2026-06-05

## Why

`CVE-2025-71176` (pytest) was the **last** remaining `pip-audit` ignore. It is
dev/test-only — pytest never ships in the production image (`requirements-dev.txt`
is not installed in prod) — so it was a justified, tracked ignore. But with #222
having cleared the jose/pyasn1 ignores, this was the one thing standing between
us and a **zero-ignore CVE gate**. `pip-audit` reports the fix as **pytest 9.0.3**.

## Exit criteria (all met)

1. `pytest` bumped to a version that clears CVE-2025-71176 (9.0.3). ✅
2. Full test suite still green on the new major (pytest 9 + pytest-asyncio 1.4). ✅
3. The last `ignore-vulns` entry removed from CI; **`pip-audit` clean with ZERO
   ignores** on both `requirements.txt` and `requirements-dev.txt`. ✅
4. Contracts 14/14; drift OK. ✅

## What changed

| File | Change |
|---|---|
| `requirements-dev.txt` | `pytest 8.3.5 → 9.0.3`; `pytest-asyncio 0.25.3 → 1.4.0` |
| `pyproject.toml` | pin `asyncio_default_fixture_loop_scope = "function"` |
| `.github/workflows/ci.yml` | remove the last `ignore-vulns` (CVE-2025-71176) → zero ignores |
| `CHANGELOG.md` | Security entry |

### Why pytest-asyncio also had to move

`pytest-asyncio==0.25.3` caps `pytest<9,>=8.2`, so pytest 9 forces a
pytest-asyncio bump. The first release that allows pytest 9 is **1.4.0**
(`pytest<10,>=8.4`, requires Python ≥3.10 — CI runs 3.11, local 3.13, both fine).
This is a 0.25 → 1.4 jump across pytest-asyncio's 1.0 rewrite, so the **whole
suite was re-run** as the real verification (a version pin you can't see fail is
not verified). It passed unchanged — `asyncio_mode = "auto"` is still the
supported config and no test used a removed/legacy API.

### Why pin the fixture loop scope

pytest-asyncio recommends setting `asyncio_default_fixture_loop_scope` explicitly
rather than relying on the implicit default (which 0.25.x warned about and which
can change across majors). Pinning it to `"function"` matches the current
behaviour and makes future pytest-asyncio upgrades deterministic. No test
behaviour changed.

## Verification

- `python -m pytest -q` → **305 passed, 3 skipped** on pytest 9.0.3 +
  pytest-asyncio 1.4.0 (identical to the pre-bump result); 308 tests collected.
- `pip-audit -r requirements.txt` and `-r requirements-dev.txt`, **no ignores** →
  **No known vulnerabilities found** on both. The CVE gate is now ignore-free.
- Contracts 14/14; drift OK.

## Note

Going forward the policy in `ci.yml` is explicit: if a new CVE appears, **fix it
at the source** (bump/replace the dependency) rather than re-adding an ignore.
Stacked on #222 (both edit the same `ci.yml` ignore block).
