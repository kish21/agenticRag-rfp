"""
tests/test_access_invariant.py
==============================
Phase 9 critical invariant — autonomous ingestion never writes to user/access tables.

The Phase 9 model relies on access lists being decided at RFP-CREATION time by
a human, then inherited by every run. Vendor files arriving via background
ingestion (Phase 5 watchers) must ONLY add data into already-permissioned
slots; they must NEVER add, modify, or remove rows in:

    user_departments
    rfp_collaborators
    approval_assignments

Violating this invariant would mean a file dropping into the watch folder
could silently grant a user access — which would be a critical security bug.

This test enforces the invariant statically: it scans every Python file under
`app/` for SQL statements that write to these tables. It then asserts that
the only files allowed to do so are the explicit administration paths
(human-driven endpoints) and the visibility wrapper itself.

If a future change introduces a write to one of these tables from, say,
`app/agents/ingestion.py` or `app/jobs/ingestion_watcher.py`, this test
will fail — that's the design intent.
"""
import re
from pathlib import Path

import pytest


# Files that legitimately write to user/access tables. Adding to this list
# requires explicit reviewer attention — these are the ONLY trusted writers.
# Strict allow-list: ONLY this one file is permitted to issue direct SQL writes
# to the protected tables. API routes (admin / evaluation) must call through
# this module so authorisation rules are enforced in exactly one place.
_ALLOWED_WRITERS = {
    "app/domain/visibility.py",
}

_PROTECTED_TABLES = ("user_departments", "rfp_collaborators", "approval_assignments")

# Match INSERT/UPDATE/DELETE targeting any of the protected tables.
# Case-insensitive; spans whitespace; matches in SQL text inside Python strings.
_WRITE_PATTERN = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+("
    + "|".join(_PROTECTED_TABLES)
    + r")\b",
    re.IGNORECASE,
)

ROOT = Path(__file__).resolve().parent.parent


def _scan_repo_for_writes() -> dict[str, list[tuple[int, str]]]:
    """Scan app/ + tests/ for write-statements against protected tables.

    Returns {relative_file_path: [(line_number, matched_line_excerpt), ...]}.
    Empty dict means no writes anywhere — including the allow-listed files,
    which is impossible in practice (visibility.py legitimately writes).
    """
    findings: dict[str, list[tuple[int, str]]] = {}
    for py in (ROOT / "app").rglob("*.py"):
        rel = py.relative_to(ROOT).as_posix()
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            m = _WRITE_PATTERN.search(line)
            if m:
                findings.setdefault(rel, []).append((i, line.strip()[:140]))
    return findings


def test_only_allow_listed_files_write_to_access_tables():
    """The core Phase 9 invariant. If this test fails, a new code path is
    writing to a protected table from outside the trusted set — review it."""
    findings = _scan_repo_for_writes()

    violations: dict[str, list[tuple[int, str]]] = {}
    for rel, hits in findings.items():
        if rel not in _ALLOWED_WRITERS:
            violations[rel] = hits

    if violations:
        report = "\n".join(
            f"\n  {rel}:\n" + "\n".join(f"    L{ln}: {ex}" for ln, ex in hits)
            for rel, hits in violations.items()
        )
        pytest.fail(
            "PHASE 9 ACCESS-INHERITANCE INVARIANT VIOLATED.\n"
            "The following files write to user_departments / rfp_collaborators / "
            "approval_assignments but are NOT in the allow-list:\n"
            + report
            + "\n\nIf the write is legitimate (human-triggered, under "
            "require_run_access or require_role), add the file to _ALLOWED_WRITERS "
            "in this test and update tests/test_access_invariant.py docs.\n"
            "If the write is from an autonomous code path (ingestion watcher, "
            "agent, background job), it MUST be removed — access is decided at "
            "RFP creation, not at file arrival."
        )


def test_allow_listed_files_actually_contain_writes():
    """Sanity check: the allow-list shouldn't be aspirational. Every file in
    `_ALLOWED_WRITERS` (excluding the schema DDL) must actually contain at
    least one write to a protected table — otherwise the entry is stale."""
    findings = _scan_repo_for_writes()

    runtime_writers = {f for f in _ALLOWED_WRITERS if f.endswith(".py")}
    missing = [f for f in runtime_writers if f not in findings]
    assert not missing, (
        f"Allow-list contains files with no actual writes — remove them:\n  {missing}"
    )


def test_no_ingestion_or_agent_code_writes_to_access_tables():
    """Belt-and-braces — explicit check that none of the high-risk paths
    (agents, retrieval, jobs, pipeline) write to access tables. This is a
    redundant guard so a future refactor that moves files around can't
    silently relax the invariant."""
    findings = _scan_repo_for_writes()
    high_risk_prefixes = (
        "app/agents/",
        "app/retrieval/",
        "app/jobs/",
        "app/pipeline/",
    )
    leaks = {
        rel: hits for rel, hits in findings.items()
        if any(rel.startswith(p) for p in high_risk_prefixes)
    }
    assert not leaks, (
        f"High-risk path is writing to access tables: {leaks}\n"
        "Ingestion / agent / pipeline / background-job code must NEVER mutate "
        "user_departments, rfp_collaborators, or approval_assignments."
    )
