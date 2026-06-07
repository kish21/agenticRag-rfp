"""
P1.9 (#60) — the Evaluation Agent injects the few-shot block into BOTH the
mandatory-check prompt and the criterion-scoring prompt, between the extracted
facts and the JSON instruction. When the bank yields "", the prompt is unchanged.

These tests prove the injection POINT wiring (placement + both paths + no-op when
empty). The rendering chain itself is covered in tests/test_few_shot_bank.py.

call_llm is mocked and captures the messages it receives — no network, no DB.

Run: python -m pytest tests/test_evaluation_few_shot_injection.py -v
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

import app.agents.evaluation as ev
from app.schemas.schema_setup import MandatoryCheck, ExtractionTarget, ScoringCriterion

SENTINEL = "<<<FEWSHOT-CALIBRATION-BLOCK>>>\n"

_CHECK = MandatoryCheck(
    check_id="chk-1", name="ISO 27001", description="must hold ISO 27001",
    what_passes="valid certificate", extraction_target_id="t1",
)
_TARGET = ExtractionTarget(
    target_id="t1", name="Certifications", description="security certs",
    fact_type="certification", is_mandatory=True,
)
_CRITERION = ScoringCriterion(
    criterion_id="crit-1", name="Security", weight=1.0,
    rubric_9_10="excellent", rubric_6_8="good", rubric_3_5="weak", rubric_0_2="absent",
    extraction_target_ids=["t1"],
)
_FACTS = [{"fact_name": "ISO 27001", "text_value": "valid", "grounding_quote": "ISO 27001 valid"}]


def _check_resp() -> str:
    return json.dumps({
        "decision": "pass", "confidence": 0.95, "reasoning": "ok",
        "evidence_used": ["ISO 27001 valid"], "contradictions_found": [],
        "decision_basis": "explicit_confirmation",
    })


def _score_resp() -> str:
    return json.dumps({
        "raw_score": 8, "confidence": 0.9, "rubric_band_applied": "6-8",
        "evidence_used": ["ISO 27001 valid"], "score_rationale": "good",
        "variance_estimate": 0.5,
    })


def _capturing_mock(resp: str):
    calls = []

    async def _fn(messages, *a, **k):
        calls.append(messages)
        return resp

    return AsyncMock(side_effect=_fn), calls


# ── mandatory check ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_check_injects_block_when_present():
    mock, calls = _capturing_mock(_check_resp())
    with patch.object(ev, "call_llm", mock), \
         patch.object(ev, "build_few_shot_block", return_value=SENTINEL) as bld:
        await ev._evaluate_mandatory_check(_CHECK, _TARGET, _FACTS, "v1", org_id="org-1")
    bld.assert_called_once_with("org-1", "check", "chk-1", "ISO 27001")
    user_msg = calls[0][1]["content"]
    assert SENTINEL in user_msg
    # placement: after the facts, before the JSON instruction
    assert user_msg.index(SENTINEL) < user_msg.index("Return JSON")
    assert user_msg.index("Extracted facts") < user_msg.index(SENTINEL)


@pytest.mark.asyncio
async def test_check_unchanged_when_block_empty():
    mock, calls = _capturing_mock(_check_resp())
    with patch.object(ev, "call_llm", mock), \
         patch.object(ev, "build_few_shot_block", return_value=""):
        await ev._evaluate_mandatory_check(_CHECK, _TARGET, _FACTS, "v1", org_id="org-1")
    assert SENTINEL not in calls[0][1]["content"]


# ── criterion score ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_criterion_injects_block_when_present():
    mock, calls = _capturing_mock(_score_resp())
    with patch.object(ev, "call_llm", mock), \
         patch.object(ev, "build_few_shot_block", return_value=SENTINEL) as bld:
        await ev._score_criterion(_CRITERION, _FACTS, "v1", org_id="org-1")
    bld.assert_called_once_with("org-1", "criterion", "crit-1", "Security")
    user_msg = calls[0][1]["content"]
    assert SENTINEL in user_msg
    assert user_msg.index(SENTINEL) < user_msg.index("Score this vendor")
    assert user_msg.index("Extracted facts") < user_msg.index(SENTINEL)


@pytest.mark.asyncio
async def test_criterion_unchanged_when_block_empty():
    mock, calls = _capturing_mock(_score_resp())
    with patch.object(ev, "call_llm", mock), \
         patch.object(ev, "build_few_shot_block", return_value=""):
        await ev._score_criterion(_CRITERION, _FACTS, "v1", org_id="org-1")
    assert SENTINEL not in calls[0][1]["content"]
