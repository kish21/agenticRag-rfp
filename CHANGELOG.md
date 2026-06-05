# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Until the first tagged release, all changes are tracked under **[Unreleased]**.

## [Unreleased]

### Added

- Dependency vulnerability scanning (`pip-audit`) in CI and Dependabot configuration.
- Security policy and responsible-disclosure process (`.github/SECURITY.md`).
- This changelog.
- Repeatable evidence-quality benchmark (`benchmark/`) with golden scenarios, a pure
  metrics library, a runner, and config-driven regression gates (`benchmark/gates.yaml`).
- Coverage-normalised vendor ranking so un-assessed criteria are not scored as zero.
- Reranker backend sourced from `.env` (`RERANKER_PROVIDER`); air-gapped default no
  longer requires HuggingFace egress, with a loud (non-blocking) degradation signal.

### Changed

- Vendor scoring now reports on a 0–10 scale end to end (fixes recommendation thresholds).
- Auth hardening: env-aware secure cookies, one account per email, session allowlist,
  and one-time hashed tokens for invite/reset.
- Customer-facing copy: "rubric" renamed to "score guide".

### Fixed

- Resolved contradictions are surfaced for human review instead of dropping the vendor.
- Vendors that never demonstrate a mandatory requirement are now rejected.
- Tenant isolation enforced via PostgreSQL row-level security.
- Retention cleanup now deletes one expired evaluation setup's vectors precisely
  (chunks are stamped with `setup_id` at ingestion) instead of wiping the whole
  org's vectors — an expired setup no longer removes the org's other live setups.

### Security

- Remediated dependency CVEs surfaced by the new pip-audit gate: pypdf 5.4.0→6.11.0,
  python-multipart 0.0.18→0.0.27, weasyprint 63.1→68.0, python-jose 3.3.0→3.4.0,
  python-dotenv 1.1.0→1.2.2, pinned starlette 1.0.1 (instrumentator 8.0.0).
- Moved `sentence-transformers` (local BGE reranker + local embeddings) to an optional
  `requirements-local.txt`, keeping `transformers`/`torch` out of the default/prod image —
  this **removes both transformers CVEs entirely** (no ignore needed) and slims the image.
  The `bge`/`local` providers now fail loud with an install hint if selected without it;
  the default `modal`+`openai` path is unaffected.
- Migrated JWT auth from `python-jose` to `PyJWT 2.13.0` (HS256 only, no crypto extra),
  dropping the `jose`/`ecdsa`/`pyasn1`/`rsa` dependency chain. This **removes two CVE
  ignores** (PYSEC-2025-185 jose JWE-bomb, CVE-2026-30922 pyasn1 DoS) with no code-
  reachability caveat — they are gone from the audited set.
- Bumped `pytest` 8.3.5→9.0.3 (with `pytest-asyncio` 0.25.3→1.4.0, required for pytest 9),
  clearing CVE-2025-71176. **The `pip-audit` gate now runs with ZERO ignores** — every
  previously-ignored CVE has been resolved at the source.

### Changed

- The default install no longer pulls heavy local ML libs. For air-gapped/local model
  inference run `pip install -r requirements.txt -r requirements-local.txt`.

[Unreleased]: https://github.com/kish21/agenticRag-rfp/commits/master
