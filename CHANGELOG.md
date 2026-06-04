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

[Unreleased]: https://github.com/kish21/agenticRag-rfp/commits/master
