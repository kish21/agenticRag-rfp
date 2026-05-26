"""
Prompt registry for Meridian AI Platform.

Load order:
  1. LangSmith Hub  (if LANGSMITH_API_KEY is set and network is reachable)
  2. Local YAML fallback in app/prompts/

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
    # ── Setup (pre-agent) ──────────────────────────────────────────────────────
    "setup/extract_rfp_criteria":    ("setup-extract-rfp-criteria",    "setup/extract_rfp_criteria.yaml"),
    "setup/generate_score_guides":   ("setup-generate-score-guides",   "setup/generate_score_guides.yaml"),
    "setup/suggest_mandatory_checks":("setup-suggest-mandatory-checks","setup/suggest_mandatory_checks.yaml"),
    "setup/interpret_criteria_sheet":("setup-interpret-criteria-sheet","setup/interpret_criteria_sheet.yaml"),
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
    """Returns True only if LANGSMITH_API_KEY is set and hub is reachable."""
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
                print(f"  [prompt] {name} <- LangSmith Hub ({langsmith_id})")

        if name not in _cache:
            _cache[name] = _load_from_yaml(yaml_file)
            print(f"  [prompt] {name} <- local YAML (LangSmith unavailable)")

    template = _cache[name]

    # Fill variables using {var} placeholders (double braces {{ }} are literal braces)
    for key, value in variables.items():
        template = template.replace("{" + key + "}", str(value))

    return template
