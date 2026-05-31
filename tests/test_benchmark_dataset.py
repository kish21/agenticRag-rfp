"""
E3 benchmark dataset integrity (exit criteria A1–A3).

CI-safe: parses the committed scenario PDFs/JSON only — no DB, no LLM, no network.
If these fail, the benchmark's answer key cannot be trusted, so no downstream
number is trustworthy either (this is the anti-hallucination floor).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domain.criteria import extract_rfp_text
from app.schemas.output_models import EvaluationSetup
from benchmark.golden_schema import ScenarioGolden

SCENARIOS = Path(__file__).resolve().parents[1] / "benchmark" / "scenarios"
REQUIRED = {"01_clean", "02_table_heavy", "03_long", "04_short",
            "05_conflicting", "06_missing_evidence"}


def _scenario_dirs() -> list[Path]:
    return sorted(d for d in SCENARIOS.iterdir() if d.is_dir())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def test_a1_all_required_scenarios_exist_and_validate():
    found = {d.name for d in _scenario_dirs()}
    assert REQUIRED <= found, f"missing scenarios: {REQUIRED - found}"
    for d in _scenario_dirs():
        ScenarioGolden.model_validate_json((d / "golden.json").read_text(encoding="utf-8"))
        EvaluationSetup.model_validate_json((d / "setup.json").read_text(encoding="utf-8"))
        assert (d / "rfp.pdf").exists()


@pytest.mark.parametrize("d", _scenario_dirs(), ids=lambda p: p.name)
def test_a2_golden_grounding_is_verbatim_in_source(d: Path):
    """Every present fact's grounding_substring must appear verbatim (whitespace-
    normalised) in its vendor PDF, as read by the pipeline's own extractor."""
    g = ScenarioGolden.model_validate_json((d / "golden.json").read_text(encoding="utf-8"))
    for v in g.vendors:
        text = _norm(extract_rfp_text((d / v.vendor_pdf).read_bytes()))
        for f in v.facts:
            if not f.present:
                continue
            assert _norm(f.grounding_substring) in text, (
                f"{d.name}/{v.vendor_id}: grounding {f.grounding_substring!r} "
                f"({f.fact_type}) not found verbatim in source PDF"
            )


def test_a2_absent_facts_have_no_grounding():
    for d in _scenario_dirs():
        g = ScenarioGolden.model_validate_json((d / "golden.json").read_text(encoding="utf-8"))
        for v in g.vendors:
            for f in v.facts:
                if not f.present:
                    assert f.grounding_substring is None


def test_a3_hard_cases_are_covered():
    goldens = {d.name: ScenarioGolden.model_validate_json(
        (d / "golden.json").read_text(encoding="utf-8")) for d in _scenario_dirs()}

    # ≥1 scenario omits a mandatory fact (missing-evidence → rejection expected)
    assert any(v.expected_rejected for g in goldens.values() for v in g.vendors)
    # ≥1 scenario has internally conflicting evidence
    assert any("conflicting" in g.stresses for g in goldens.values())
    # ≥1 long-doc scenario (retrieval stress) and ≥1 table-heavy
    assert any("long" in g.stresses for g in goldens.values())
    assert any("tables" in g.stresses for g in goldens.values())
    # ≥1 scenario expects an 'insufficient' scoring outcome (the no-forced-score case)
    assert any(c.expectation == "insufficient"
               for g in goldens.values() for v in g.vendors for c in v.criteria)
