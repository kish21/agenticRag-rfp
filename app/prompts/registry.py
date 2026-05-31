"""
Prompt registry for Meridian AI Platform.

Source of truth:
  1. Local YAML in app/prompts/  — AUTHORITATIVE, used by default on every run, so
     the committed repo deterministically defines runtime prompt behaviour.
  2. LangSmith Hub — OPT-IN only (set PROMPTS_USE_HUB=true). The Hub is a *publish*
     target via tools/push_prompts.py, not a runtime override.

Why: the Hub used to be loaded first and silently overrode the committed YAML
whenever it was network-reachable — so the same code ran different (often stale)
prompts depending on connectivity (e.g. the Hub copy of explanation/generate_narrative
was 3x smaller/older than the local one). Local-first makes the folder the single
source of truth.

Call get_prompt(name, **vars) — returns the filled prompt string ready for call_llm().
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

_PROMPTS_DIR = Path(__file__).parent

# Map short names → (langsmith_identifier, local_yaml_file)
# Key format: "agent/prompt_name"  matches LangSmith Hub namespace: meridian/agent/prompt-name
_REGISTRY: dict[str, tuple[str, str]] = {
    # ── Setup (Agent 00) ───────────────────────────────────────────────────────
    "setup/extract_rfp_criteria":    ("setup-extract-rfp-criteria",    "setup/extract_rfp_criteria.yaml"),
    "setup/generate_score_guides":   ("setup-generate-score-guides",   "setup/generate_score_guides.yaml"),
    "setup/suggest_mandatory_checks":("setup-suggest-mandatory-checks","setup/suggest_mandatory_checks.yaml"),
    "setup/interpret_criteria_sheet":("setup-interpret-criteria-sheet","setup/interpret_criteria_sheet.yaml"),

    # ── Retrieval (Agent 02) ───────────────────────────────────────────────────
    "retrieval/rewrite_query":        ("retrieval-rewrite-query",        "retrieval/rewrite_query.yaml"),
    "retrieval/hyde_vendor_response": ("retrieval-hyde-vendor-response", "retrieval/hyde_vendor_response.yaml"),
    "retrieval/hyde_rfp_requirement": ("retrieval-hyde-rfp-requirement", "retrieval/hyde_rfp_requirement.yaml"),
    "retrieval/hyde_policy_document": ("retrieval-hyde-policy-document", "retrieval/hyde_policy_document.yaml"),

    # ── Extraction (Agent 03) ──────────────────────────────────────────────────
    "extraction/extract_facts":       ("extraction-extract-facts",       "extraction/extract_facts.yaml"),
    "extraction/retry_extract":       ("extraction-retry-extract",       "extraction/retry_extract.yaml"),

    # ── Evaluation (Agent 04) ──────────────────────────────────────────────────
    "evaluation/verify_threshold":    ("evaluation-verify-threshold",    "evaluation/verify_threshold.yaml"),
    "evaluation/evaluate_check":      ("evaluation-evaluate-check",      "evaluation/evaluate_check.yaml"),
    "evaluation/score_criterion":     ("evaluation-score-criterion",     "evaluation/score_criterion.yaml"),

    # ── Comparator (Agent 05) ──────────────────────────────────────────────────
    "comparator/compare_criterion":   ("comparator-compare-criterion",   "comparator/compare_criterion.yaml"),

    # ── Decision (Agent 06) ───────────────────────────────────────────────────
    "decision/extract_evidence":      ("decision-extract-evidence",      "decision/extract_evidence.yaml"),

    # ── Explanation (Agent 07) ────────────────────────────────────────────────
    "explanation/generate_narrative": ("explanation-generate-narrative", "explanation/generate_narrative.yaml"),

    # ── Critic-as-controller (Phase 2c) ────────────────────────────────────────
    "critic/retry_feedback":          ("critic-retry-feedback",          "critic/retry_feedback.yaml"),
}

# In-process cache: name → raw template string
_cache: dict[str, str] = {}


def _langsmith_session():
    """requests.Session with SSL verification disabled for LangSmith (Norton MITM on local dev)."""
    import requests
    session = requests.Session()
    if os.getenv("LANGSMITH_VERIFY_SSL", "true").lower() == "false":
        session.verify = False
    return session


@lru_cache(maxsize=1)
def _langsmith_available() -> bool:
    """Whether to load prompts from the LangSmith Hub.

    Local YAML is authoritative and used by DEFAULT, so the Hub is strictly
    opt-in: it is consulted only when PROMPTS_USE_HUB=true (and the key is set and
    the hub is reachable). PROMPTS_FORCE_LOCAL=true is still honoured as a hard
    override. Default (neither set) → local YAML, deterministically."""
    if os.getenv("PROMPTS_USE_HUB", "false").lower() != "true":
        return False
    if os.getenv("PROMPTS_FORCE_LOCAL", "false").lower() == "true":
        return False
    if not os.getenv("LANGSMITH_API_KEY"):
        return False
    try:
        from langsmith import Client
        Client(session=_langsmith_session()).list_prompts(limit=1)  # lightweight probe
        return True
    except Exception:
        return False


def _load_from_langsmith(identifier: str) -> str | None:
    """Pull prompt template from LangSmith Hub. Returns raw template string or None."""
    try:
        from langsmith import Client
        prompt_obj = Client(session=_langsmith_session()).pull_prompt(identifier)
        # pull_prompt returns a LangChain PromptTemplate or ChatPromptTemplate
        if hasattr(prompt_obj, "template"):
            return prompt_obj.template
        # ChatPromptTemplate — extract first human message template
        if hasattr(prompt_obj, "messages"):
            for msg in prompt_obj.messages:
                if hasattr(msg, "prompt") and hasattr(msg.prompt, "template"):
                    return msg.prompt.template
        return str(prompt_obj)
    except Exception:
        return None


def _load_from_yaml(yaml_file: str) -> str:
    """Load prompt template from local YAML file. Raises if file missing."""
    path = _PROMPTS_DIR / yaml_file
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["template"]


def get_prompt(name: str, **variables: str) -> str:
    """
    Returns the filled prompt string for the given name.

    Args:
        name: short registry key, e.g. "extract_rfp_criteria"
        **variables: template variables to substitute

    Raises:
        KeyError: if name is not in the registry
    """
    if name not in _REGISTRY:
        raise KeyError(f"Unknown prompt: {name!r}. Available: {list(_REGISTRY)}")

    # Load template (cached after first load)
    if name not in _cache:
        langsmith_id, yaml_file = _REGISTRY[name]
        template: str | None = None

        if _langsmith_available():
            template = _load_from_langsmith(langsmith_id)
            if template:
                _cache[name] = template
                print(f"  [prompt] {name} <- LangSmith Hub (PROMPTS_USE_HUB={langsmith_id})")

        if name not in _cache:
            _cache[name] = _load_from_yaml(yaml_file)
            print(f"  [prompt] {name} <- local YAML (authoritative)")

    template = _cache[name]

    # Substitute ONLY the named input variables, e.g. {schema} -> value. This is a
    # targeted str.replace, NOT str.format(), so a bare "{" in the template is safe
    # and does NOT need escaping. WARNING: "{{ }}" is NOT collapsed to "{ }" — it is
    # passed to the model verbatim. Author JSON examples with single braces.
    # (Some setup/* YAMLs still use "{{ }}" from a LangChain round-trip — tracked as
    # a prompt-content cleanup in the refinement pass; see docs/dev/BACKLOG.md.)
    for key, value in variables.items():
        template = template.replace("{" + key + "}", str(value))

    return template
