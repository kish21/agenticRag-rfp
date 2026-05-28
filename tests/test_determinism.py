"""
tests/test_determinism.py
=========================
Phase 1 exit-criterion test: verifies that the Phase 1 determinism plumbing in
app/providers/llm.py works correctly.

These tests do NOT hit real LLM providers. They:
  1. Verify stable_seed() is deterministic and well-distributed.
  2. Verify call_llm() auto-derives a seed from messages when seed=None.
  3. Verify the Anthropic branch (which previously dropped temperature) now
     forwards it to client.messages.create.
  4. Verify the OpenAI-family branches forward seed to the SDK.

Run:
    python -m pytest tests/test_determinism.py -v
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.providers.llm import call_llm, stable_seed  # noqa: E402


# ── stable_seed ───────────────────────────────────────────────────────────────

class TestStableSeed:
    def test_deterministic_same_input(self):
        assert stable_seed("a", "b", "c") == stable_seed("a", "b", "c")

    def test_different_input_different_seed(self):
        assert stable_seed("a") != stable_seed("b")
        assert stable_seed("a", "b") != stable_seed("b", "a")

    def test_returns_32bit_int(self):
        s = stable_seed("test")
        assert isinstance(s, int)
        assert 0 <= s < 2**32

    def test_handles_unicode_and_empty(self):
        # Should not raise on weird inputs
        stable_seed("")
        stable_seed("héllo", "wörld")
        stable_seed("", "", "")


# ── call_llm seed plumbing ────────────────────────────────────────────────────

class TestCallLLMSeedAutoDerive:
    """seed=None → derived from messages; same messages → same seed."""

    @pytest.mark.asyncio
    async def test_same_messages_produce_same_auto_seed(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        seeds_captured: list[int] = []

        async def fake_create(**kwargs):
            seeds_captured.append(kwargs.get("seed"))
            # Build minimal OpenAI-shaped response
            from types import SimpleNamespace
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

        with patch("app.providers.llm.get_llm_client") as mock_client, \
             patch("app.config.settings.llm_provider", "openai"):
            mock_client.return_value.chat.completions.create = fake_create
            msgs = [{"role": "user", "content": "hello world"}]
            await call_llm(msgs)
            await call_llm(msgs)

        assert len(seeds_captured) == 2
        assert seeds_captured[0] is not None
        assert seeds_captured[0] == seeds_captured[1], \
            "Same messages must auto-derive the same seed"

    @pytest.mark.asyncio
    async def test_different_messages_produce_different_seeds(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        seeds_captured: list[int] = []

        async def fake_create(**kwargs):
            seeds_captured.append(kwargs.get("seed"))
            from types import SimpleNamespace
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

        with patch("app.providers.llm.get_llm_client") as mock_client, \
             patch("app.config.settings.llm_provider", "openai"):
            mock_client.return_value.chat.completions.create = fake_create
            await call_llm([{"role": "user", "content": "first"}])
            await call_llm([{"role": "user", "content": "second"}])

        assert seeds_captured[0] != seeds_captured[1]

    @pytest.mark.asyncio
    async def test_explicit_seed_overrides_auto(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        seeds_captured: list[int] = []

        async def fake_create(**kwargs):
            seeds_captured.append(kwargs.get("seed"))
            from types import SimpleNamespace
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

        with patch("app.providers.llm.get_llm_client") as mock_client, \
             patch("app.config.settings.llm_provider", "openai"):
            mock_client.return_value.chat.completions.create = fake_create
            await call_llm([{"role": "user", "content": "x"}], seed=42)

        assert seeds_captured[0] == 42


# ── Anthropic temperature fix ─────────────────────────────────────────────────

class TestAnthropicTemperaturePassed:
    """Regression test for the Phase 1 bug: Anthropic branch silently dropped temperature."""

    @pytest.mark.asyncio
    async def test_anthropic_branch_passes_temperature_to_sdk(self):
        captured: dict = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            from types import SimpleNamespace
            return SimpleNamespace(
                content=[SimpleNamespace(text="ok")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

        with patch("app.providers.llm.get_llm_client") as mock_client, \
             patch("app.config.settings.llm_provider", "anthropic"):
            mock_client.return_value.messages.create = fake_create
            await call_llm(
                [{"role": "user", "content": "test"}],
                temperature=0.0,
            )

        assert "temperature" in captured, \
            "Anthropic branch must forward temperature to client.messages.create"
        assert captured["temperature"] == 0.0
