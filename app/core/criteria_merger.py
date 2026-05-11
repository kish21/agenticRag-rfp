"""
Merges org criteria, department criteria, and RFP-extracted
criteria into one EvaluationSetup.
All LLM calls use call_llm() — never OpenAI directly.
"""
import json
import uuid
from app.db.fact_store import get_engine
from app.core.llm_provider import call_llm
import sqlalchemy as sa


def get_org_criteria(org_id: str) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(sa.text(
            "SET LOCAL app.current_org_id = :oid"
        ), {"oid": org_id})
        rows = conn.execute(sa.text("""
            SELECT template_id::text, check_type, name,
                   description, what_passes, default_weight,
                   rubric, is_locked
            FROM org_criteria_templates
            WHERE org_id = :org_id
            ORDER BY check_type, created_at
        """), {"org_id": org_id}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_dept_criteria(org_id: str, department: str) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(sa.text(
            "SET LOCAL app.current_org_id = :oid"
        ), {"oid": org_id})
        rows = conn.execute(sa.text("""
            SELECT template_id::text, check_type, name,
                   description, what_passes, default_weight,
                   rubric, is_locked
            FROM dept_criteria_templates
            WHERE org_id = :org_id
            AND department = :department
            ORDER BY check_type, created_at
        """), {"org_id": org_id, "department": department}).fetchall()
    return [dict(r._mapping) for r in rows]


def extract_rfp_text(rfp_bytes: bytes) -> str:
    """Extract text from RFP PDF using pypdf (already in requirements)."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(rfp_bytes))
        pages = reader.pages[:15]
        return " ".join(
            (p.extract_text() or "") for p in pages
        )
    except Exception as e:
        print(f"RFP text extraction failed: {e}")
        return ""


async def extract_criteria_from_rfp(rfp_text: str) -> dict:
    """
    Uses call_llm() to extract mandatory requirements and
    scoring criteria from RFP text.
    Falls back to empty lists on failure.
    """
    if not rfp_text or len(rfp_text.strip()) < 100:
        return {"mandatory_checks": [], "scoring_criteria": []}

    prompt = f"""Read this RFP and extract evaluation criteria.

Return ONLY valid JSON:
{{
  "mandatory_checks": [
    {{
      "name": "short name",
      "description": "what vendor must provide",
      "what_passes": "what constitutes passing",
      "page_reference": "section/page if found"
    }}
  ],
  "scoring_criteria": [
    {{
      "name": "criterion name",
      "weight": 0.35,
      "description": "what is scored",
      "rubric_9_10": "outstanding evidence",
      "rubric_6_8": "good evidence",
      "rubric_3_5": "adequate evidence",
      "rubric_0_2": "poor or absent",
      "page_reference": "section/page if found"
    }}
  ]
}}

Rules:
- weights must sum to 1.0
- convert percentages to decimals (35% = 0.35)
- if no weight stated distribute evenly
- return only JSON no prose or markdown

RFP TEXT:
{rfp_text[:6000]}"""

    try:
        response = await call_llm(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        clean = response.strip()
        if "```" in clean:
            parts = clean.split("```")
            clean = parts[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean.strip())
    except Exception as e:
        print(f"RFP criteria LLM extraction failed: {e}")
        return {"mandatory_checks": [], "scoring_criteria": []}


def merge_criteria(
    org_criteria: list[dict],
    dept_criteria: list[dict],
    rfp_criteria: dict,
    department: str,
    rfp_id: str,
    org_id: str,
) -> dict:
    """
    Merges three sources. Priority: org > dept > rfp.
    Deduplicates by name (case-insensitive).
    Each criterion gets a source field: org|dept|rfp.
    Returns dict compatible with EvaluationSetup model.
    """
    mandatory_checks = []
    scoring_criteria = []
    mandatory_names = set()
    scoring_names = set()

    # 1. Org criteria (highest priority, may be locked)
    for c in org_criteria:
        name_key = c["name"].lower()
        if c["check_type"] == "mandatory":
            tid = c["template_id"][:8].upper()
            mandatory_checks.append({
                "check_id": f"MC-ORG-{tid}",
                "name": c["name"],
                "description": c["description"],
                "what_passes": c["what_passes"],
                "extraction_target_id": f"ET-ORG-{tid}",
                "source": "org",
                "is_locked": c["is_locked"],
            })
            mandatory_names.add(name_key)
        elif c["check_type"] == "scoring":
            tid = c["template_id"][:8].upper()
            scoring_criteria.append({
                "criterion_id": f"SC-ORG-{tid}",
                "name": c["name"],
                "weight": float(c["default_weight"]),
                "rubric_9_10": c.get("rubric", {}).get("9_10", ""),
                "rubric_6_8":  c.get("rubric", {}).get("6_8",  ""),
                "rubric_3_5":  c.get("rubric", {}).get("3_5",  ""),
                "rubric_0_2":  c.get("rubric", {}).get("0_2",  ""),
                "extraction_target_ids": [],
                "source": "org",
                "is_locked": c["is_locked"],
            })
            scoring_names.add(name_key)

    # 2. Dept criteria (skip duplicates)
    for c in dept_criteria:
        name_key = c["name"].lower()
        if c["check_type"] == "mandatory":
            if name_key not in mandatory_names:
                tid = c["template_id"][:8].upper()
                mandatory_checks.append({
                    "check_id": f"MC-DEPT-{tid}",
                    "name": c["name"],
                    "description": c["description"],
                    "what_passes": c["what_passes"],
                    "extraction_target_id": f"ET-DEPT-{tid}",
                    "source": "dept",
                    "is_locked": c["is_locked"],
                })
                mandatory_names.add(name_key)
        elif c["check_type"] == "scoring":
            if name_key not in scoring_names:
                tid = c["template_id"][:8].upper()
                scoring_criteria.append({
                    "criterion_id": f"SC-DEPT-{tid}",
                    "name": c["name"],
                    "weight": float(c["default_weight"]),
                    "rubric_9_10": c.get("rubric", {}).get("9_10", ""),
                    "rubric_6_8":  c.get("rubric", {}).get("6_8",  ""),
                    "rubric_3_5":  c.get("rubric", {}).get("3_5",  ""),
                    "rubric_0_2":  c.get("rubric", {}).get("0_2",  ""),
                    "extraction_target_ids": [],
                    "source": "dept",
                    "is_locked": c["is_locked"],
                })
                scoring_names.add(name_key)

    # 3. RFP-extracted criteria (skip duplicates)
    for c in rfp_criteria.get("mandatory_checks", []):
        name_key = c["name"].lower()
        if name_key not in mandatory_names:
            mc_id = str(uuid.uuid4())[:8].upper()
            mandatory_checks.append({
                "check_id": f"MC-RFP-{mc_id}",
                "name": c["name"],
                "description": c.get("description", ""),
                "what_passes": c.get("what_passes", ""),
                "extraction_target_id": f"ET-RFP-{mc_id}",
                "source": "rfp",
                "is_locked": False,
                "page_reference": c.get("page_reference", ""),
            })
            mandatory_names.add(name_key)

    for c in rfp_criteria.get("scoring_criteria", []):
        name_key = c["name"].lower()
        if name_key not in scoring_names:
            sc_id = str(uuid.uuid4())[:8].upper()
            scoring_criteria.append({
                "criterion_id": f"SC-RFP-{sc_id}",
                "name": c["name"],
                "weight": float(c.get("weight", 0.0)),
                "rubric_9_10": c.get("rubric_9_10", ""),
                "rubric_6_8":  c.get("rubric_6_8",  ""),
                "rubric_3_5":  c.get("rubric_3_5",  ""),
                "rubric_0_2":  c.get("rubric_0_2",  ""),
                "extraction_target_ids": [],
                "source": "rfp",
                "is_locked": False,
                "page_reference": c.get("page_reference", ""),
            })
            scoring_names.add(name_key)

    # If no scoring criteria found fall back to even distribution
    if not scoring_criteria:
        return {
            "mandatory_checks": mandatory_checks,
            "scoring_criteria": [],
            "extraction_targets": _build_targets(mandatory_checks, []),
            "source": "merged_empty",
        }

    # Normalise weights to sum to 1.0
    total = sum(c["weight"] for c in scoring_criteria)
    if total == 0:
        even = round(1.0 / len(scoring_criteria), 3)
        for c in scoring_criteria:
            c["weight"] = even
    elif abs(total - 1.0) > 0.01:
        for c in scoring_criteria:
            c["weight"] = round(c["weight"] / total, 3)

    extraction_targets = _build_targets(mandatory_checks, scoring_criteria)
    for sc in scoring_criteria:
        tid = f"ET-SC-{sc['criterion_id'][-8:]}"
        sc["extraction_target_ids"] = [tid]

    return {
        "mandatory_checks": mandatory_checks,
        "scoring_criteria": scoring_criteria,
        "extraction_targets": extraction_targets,
        "total_weight": round(
            sum(c["weight"] for c in scoring_criteria), 3
        ),
        "source": "merged",
    }


def _build_targets(
    mandatory_checks: list[dict],
    scoring_criteria: list[dict],
) -> list[dict]:
    targets = []
    for mc in mandatory_checks:
        targets.append({
            "target_id": mc["extraction_target_id"],
            "name": mc["name"],
            "description": mc.get("what_passes", mc["name"]),
            "fact_type": "custom",
            "is_mandatory": True,
            "feeds_check_id": mc["check_id"],
            "source": mc.get("source", "rfp"),
        })
    for sc in scoring_criteria:
        tid = f"ET-SC-{sc['criterion_id'][-8:]}"
        targets.append({
            "target_id": tid,
            "name": sc["name"],
            "description": f"Find evidence for: {sc['name']}",
            "fact_type": "custom",
            "is_mandatory": False,
            "feeds_criterion_id": sc["criterion_id"],
            "source": sc.get("source", "rfp"),
        })
    return targets
