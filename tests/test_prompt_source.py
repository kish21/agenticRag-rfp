"""
Prompt source-of-truth: local YAML is authoritative; LangSmith Hub is opt-in.

CI-safe (no network). Guards the determinism fix: the committed prompt folder is
what runs by default, regardless of whether a LANGSMITH_API_KEY happens to be set
or the Hub is reachable — so prompt behaviour is reproducible.
"""
from __future__ import annotations

import app.prompts.registry as R


def test_local_is_authoritative_by_default(monkeypatch):
    # Key set + Hub would be reachable, but no opt-in → must NOT use the Hub.
    monkeypatch.delenv("PROMPTS_USE_HUB", raising=False)
    monkeypatch.delenv("PROMPTS_FORCE_LOCAL", raising=False)
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key-must-be-ignored")
    R._langsmith_available.cache_clear()
    assert R._langsmith_available() is False


def test_force_local_overrides_even_with_hub_opt_in(monkeypatch):
    monkeypatch.setenv("PROMPTS_USE_HUB", "true")
    monkeypatch.setenv("PROMPTS_FORCE_LOCAL", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake")
    R._langsmith_available.cache_clear()
    assert R._langsmith_available() is False


def test_get_prompt_loads_local_yaml(monkeypatch):
    monkeypatch.delenv("PROMPTS_USE_HUB", raising=False)
    R._langsmith_available.cache_clear()
    R._cache.clear()
    text = R.get_prompt("evaluation/score_criterion")
    assert isinstance(text, str) and len(text) > 0


def test_every_registry_prompt_has_a_local_yaml():
    # Local being authoritative means every registered prompt MUST resolve locally.
    R._cache.clear()
    monkeypatch_free = R._REGISTRY
    for name in monkeypatch_free:
        text = R._load_from_yaml(R._REGISTRY[name][1])
        assert text and text.strip(), f"{name}: empty/missing local YAML"
