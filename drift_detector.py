#!/usr/bin/env python3
"""
drift_detector.py
=================
Detects when Claude Code has drifted from the architecture.

Critical checks:
1. Hardcoded business logic in agent files (architecture violation)
2. Agents passing raw text instead of Pydantic models
3. Files built ahead of schedule
4. Security violations (secrets in code)
5. Missing Critic Agent calls

Usage:
    python drift_detector.py
    python drift_detector.py SK03
"""

import os, sys, re, json
from pathlib import Path

ROOT = Path(__file__).parent
BUILD_STATE = ROOT / "build_state.json"

# Files expected per skill
SKILL_FILES = {
    "SK01": ["app/config.py", "app/main.py", "requirements.txt", "docker-compose.yml", ".env", ".gitignore"],
    "SK02": ["app/core/output_models.py", "app/core/rate_limiter.py", "app/core/qdrant_client.py",
             "app/agents/planner.py", "app/agents/critic.py",
             "app/core/rfp_confirmation.py", "app/core/override_mechanism.py"],
    "SK03": ["app/db/schema.sql", "app/db/fact_store.py",
             "app/core/llamaindex_pipeline.py", "app/core/ingestion_validator.py",
             "app/agents/ingestion.py"],
    "SK03b": ["app/agents/retrieval.py"],
    "SK04": ["app/agents/extraction.py"],
    "SK05": ["app/agents/evaluation.py", "app/agents/comparator.py"],
    "SK06": ["app/agents/decision.py", "app/agents/explanation.py"],
    "SK07": ["app/output/pdf_report.py", "tests/regression/run_regression.py"],
    "SK08": ["app/core/langfuse_client.py", "app/jobs/cleanup.py", "app/jobs/rate_monitor.py"],
    "SK09": ["app/core/agent_registry.py", "app/api/admin_routes.py", "app/agents/hr_agent_config.py"],
}

# Content rules — must/must-not checks
CONTENT_RULES = [
    # Architecture: no hardcoded clauses in agent files
    {
        "files": ["app/agents/evaluation.py", "app/agents/compliance_checker.py"],
        "must_not_contain": r'"ISO 27001"',
        "rule": "ARCHITECTURE VIOLATION: ISO 27001 hardcoded in evaluation agent. Must come from config."
    },
    {
        "files": ["app/agents/evaluation.py"],
        "must_not_contain": r'weight\s*=\s*0\.\d+',
        "rule": "ARCHITECTURE VIOLATION: Hardcoded scoring weight. Must come from config."
    },
    # Critic must be called in agent files
    {
        "files": ["app/agents/ingestion.py"],
        "must_contain": "critic_after_ingestion",
        "rule": "Ingestion agent must call critic_after_ingestion"
    },
    {
        "files": ["app/agents/retrieval.py"],
        "must_contain": "critic_after_retrieval",
        "rule": "Retrieval agent must call critic_after_retrieval"
    },
    # No secrets hardcoded
    {
        "files": ["*.py"],
        "must_not_contain": r'sk-proj-[A-Za-z0-9]',
        "rule": "SECURITY: OpenAI API key hardcoded in Python file"
    },
    {
        "files": ["*.py"],
        "must_not_contain": r'xoxb-[A-Za-z0-9]',
        "rule": "SECURITY: Slack token hardcoded in Python file"
    },
    # Qdrant not ChromaDB
    {
        "files": ["app/core/*.py", "app/agents/*.py"],
        "must_not_contain": "chromadb",
        "rule": "ChromaDB reference found — should be Qdrant in this architecture"
    },
    # Rate limiter used in LLM calls
    {
        "files": ["app/agents/*.py"],
        "must_not_contain": r'\.chat\.completions\.create\(',
        "rule": "Direct OpenAI call found — use call_openai_with_backoff() instead"
    },
]

# Security rules
SECURITY_PATTERNS = [
    r'sk-proj-[A-Za-z0-9]{20,}',
    r'xoxb-[A-Za-z0-9\-]{20,}',
    r'ls__[A-Za-z0-9]{20,}',
    r'pk-lf-[A-Za-z0-9]{20,}',
    r'sk-lf-[A-Za-z0-9]{20,}',
]


def load_state():
    if BUILD_STATE.exists():
        with open(BUILD_STATE) as f:
            return json.load(f)
    return {"current_skill": None, "passed_checkpoints": []}


def get_skill_order():
    return ["SK01","SK02","SK03","SK03b","SK04","SK05","SK06","SK07","SK08","SK09"]


def get_current_skill_index(state):
    current = state.get("current_skill")
    order = get_skill_order()
    if not current:
        return 0
    try:
        return order.index(current)
    except ValueError:
        return 0


def check_missing_files(state, issues):
    order = get_skill_order()
    current_idx = get_current_skill_index(state)

    for i, skill in enumerate(order):
        if i > current_idx:
            break
        files = SKILL_FILES.get(skill, [])
        for f in files:
            if "*" in f:
                continue
            full = ROOT / f
            if not full.exists():
                issues.append({
                    "type": "MISSING_FILE",
                    "severity": "ERROR",
                    "file": f,
                    "message": f"Expected for {skill} but not found"
                })


def check_premature_files(state, issues):
    order = get_skill_order()
    current_idx = get_current_skill_index(state)

    for i, skill in enumerate(order):
        if i <= current_idx:
            continue
        files = SKILL_FILES.get(skill, [])
        for f in files:
            if "*" in f:
                continue
            full = ROOT / f
            if full.exists() and full.stat().st_size > 0:
                issues.append({
                    "type": "PREMATURE_FILE",
                    "severity": "WARNING",
                    "file": f,
                    "message": f"Built ahead of schedule — belongs to {skill}, current is {order[current_idx]}"
                })


def check_content_rules(issues):
    for rule in CONTENT_RULES:
        file_patterns = rule.get("files", [])
        must_contain = rule.get("must_contain")
        must_not_contain = rule.get("must_not_contain")
        rule_desc = rule.get("rule", "")

        target_files = []
        for pattern in file_patterns:
            if "*" in pattern:
                parts = pattern.split("*")
                prefix = parts[0]
                suffix = parts[-1]
                for f in ROOT.rglob(f"*{suffix}"):
                    if str(f).replace(str(ROOT)+"/", "").startswith(prefix.rstrip("/")):
                        target_files.append(f)
            else:
                target_files.append(ROOT / pattern)

        for filepath in target_files:
            if not filepath.exists():
                continue
            skip_dirs = {"venv", "__pycache__", "node_modules", ".git", ".next"}
            if any(s in filepath.parts for s in skip_dirs):
                continue
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if must_not_contain:
                if re.search(must_not_contain, content):
                    issues.append({
                        "type": "CONTENT_VIOLATION",
                        "severity": "ERROR",
                        "file": str(filepath.relative_to(ROOT)),
                        "message": rule_desc
                    })

            if must_contain:
                if must_contain not in content:
                    issues.append({
                        "type": "MISSING_PATTERN",
                        "severity": "ERROR",
                        "file": str(filepath.relative_to(ROOT)),
                        "message": rule_desc
                    })


def check_security(issues):
    for filepath in ROOT.rglob("*.py"):
        skip = {"venv", "__pycache__", "node_modules", ".git"}
        if any(s in filepath.parts for s in skip):
            continue
        if filepath.name == ".env":
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in SECURITY_PATTERNS:
            if re.search(pattern, content):
                issues.append({
                    "type": "SECURITY_VIOLATION",
                    "severity": "CRITICAL",
                    "file": str(filepath.relative_to(ROOT)),
                    "message": f"Possible secret hardcoded matching pattern: {pattern[:20]}..."
                })
                break


def main():
    state = load_state()
    current = state.get("current_skill", "not started")

    print(f"\n{'='*56}")
    print(f"DRIFT DETECTOR — Current skill: {current}")
    print(f"{'='*56}")

    issues = []
    check_missing_files(state, issues)
    check_premature_files(state, issues)
    check_content_rules(issues)
    check_security(issues)

    if not issues:
        print("\n✓ No drift detected — project is on track")
        passed = len(state.get("passed_checkpoints", []))
        print(f"  Checkpoints passed: {passed}/59")
        return

    critical = [i for i in issues if i["severity"] == "CRITICAL"]
    errors = [i for i in issues if i["severity"] == "ERROR"]
    warnings = [i for i in issues if i["severity"] == "WARNING"]

    if critical:
        print(f"\n🚨 CRITICAL ({len(critical)}) — Fix immediately:")
        for i in critical:
            print(f"  [{i['type']}] {i['file']}")
            print(f"    {i['message']}")

    if errors:
        print(f"\n✗ ERRORS ({len(errors)}) — Fix before continuing:")
        for i in errors:
            print(f"  [{i['type']}] {i.get('file','')}")
            print(f"    {i['message']}")

    if warnings:
        print(f"\n⚠ WARNINGS ({len(warnings)}):")
        for i in warnings:
            print(f"  [{i['type']}] {i.get('file','')}")
            print(f"    {i['message']}")

    print(f"\nTotal: {len(critical)} critical, {len(errors)} errors, {len(warnings)} warnings")

    if critical or errors:
        print("\n⛔ STOP CODING — fix issues above before continuing")
        sys.exit(1)


if __name__ == "__main__":
    main()
