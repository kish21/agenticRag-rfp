"""
Tests for criteria_merger.merge_criteria deduplication — issue #22.
No DB, no LLM: unit-level tests only.
"""
import pytest
from app.domain.criteria import merge_criteria, _normalize_name


# ── _normalize_name ───────────────────────────────────────────────────────────

def test_normalize_strips_certification_suffix():
    assert _normalize_name("ISO 27001 Certification") == _normalize_name("ISO 27001")

def test_normalize_strips_compliance_suffix():
    assert _normalize_name("GDPR Compliance") == _normalize_name("GDPR")

def test_normalize_strips_requirement_suffix():
    assert _normalize_name("PI Insurance Requirement") == _normalize_name("PI Insurance")

def test_normalize_case_insensitive():
    assert _normalize_name("ISO 27001") == _normalize_name("iso 27001")

def test_normalize_strips_punctuation():
    assert _normalize_name("ISO-27001") == _normalize_name("ISO 27001")


# ── merge_criteria deduplication ──────────────────────────────────────────────

def _org_row(name: str, check_type: str = "mandatory") -> dict:
    return {
        "template_id": "aabbccdd-eeff-0011-2233-445566778899",
        "check_type": check_type,
        "name": name,
        "description": f"Description for {name}",
        "what_passes": "Evidence provided",
        "default_weight": 0.50,
        "rubric": {"9_10": "", "6_8": "", "3_5": "", "0_2": ""},
        "is_locked": False,
    }


def test_exact_name_dedup():
    """Org template + identical RFP extraction → 1 check, not 2."""
    org = [_org_row("ISO 27001")]
    rfp = {"mandatory_checks": [{"name": "ISO 27001", "description": "", "what_passes": ""}]}
    result = merge_criteria(org, [], rfp, "IT", "rfp-1", "org-1")
    names = [c["name"] for c in result["mandatory_checks"]]
    assert names.count("ISO 27001") == 1, f"Expected 1, got: {names}"


def test_suffix_variant_dedup():
    """'ISO 27001' from org + 'ISO 27001 Certification' from RFP → 1 check."""
    org = [_org_row("ISO 27001")]
    rfp = {"mandatory_checks": [{"name": "ISO 27001 Certification", "description": "", "what_passes": ""}]}
    result = merge_criteria(org, [], rfp, "IT", "rfp-1", "org-1")
    assert len(result["mandatory_checks"]) == 1, (
        f"Duplicate check survived: {[c['name'] for c in result['mandatory_checks']]}"
    )


def test_pi_insurance_dedup():
    """'PI Insurance' from org + 'PI Insurance Requirement' from RFP → 1 check."""
    org = [_org_row("PI Insurance")]
    rfp = {"mandatory_checks": [{"name": "PI Insurance Requirement", "description": "", "what_passes": ""}]}
    result = merge_criteria(org, [], rfp, "Procurement", "rfp-1", "org-1")
    assert len(result["mandatory_checks"]) == 1, (
        f"Duplicate survived: {[c['name'] for c in result['mandatory_checks']]}"
    )


def test_org_source_wins_over_rfp():
    """When dedup fires, the org-sourced check is kept (not the RFP one)."""
    org = [_org_row("ISO 27001")]
    rfp = {"mandatory_checks": [{"name": "ISO 27001 Certification", "description": "RFP version", "what_passes": ""}]}
    result = merge_criteria(org, [], rfp, "IT", "rfp-1", "org-1")
    assert result["mandatory_checks"][0]["source"] == "org"


def test_genuinely_different_checks_both_survive():
    """Two actually different checks must both appear."""
    org = [_org_row("ISO 27001"), _org_row("GDPR")]
    rfp = {"mandatory_checks": [{"name": "Cyber Essentials", "description": "", "what_passes": ""}]}
    result = merge_criteria(org, [], rfp, "IT", "rfp-1", "org-1")
    assert len(result["mandatory_checks"]) == 3


def test_dept_dedup_against_org():
    """Dept template with same normalized name as org template → only org version kept."""
    org = [_org_row("ISO 27001")]
    dept = [_org_row("ISO 27001 Compliance")]
    rfp = {"mandatory_checks": []}
    result = merge_criteria(org, dept, rfp, "IT", "rfp-1", "org-1")
    assert len(result["mandatory_checks"]) == 1
    assert result["mandatory_checks"][0]["source"] == "org"
