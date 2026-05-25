"""
Merges org criteria, department criteria, and RFP-extracted
criteria into one EvaluationSetup.
All LLM calls use call_llm() — never OpenAI directly.
"""
import json
import re
import uuid
from app.db.fact_store import get_engine
from app.providers.llm import call_llm
import sqlalchemy as sa

# Common suffixes the LLM appends that don't change the meaning of a check.
# Stripping these lets "ISO 27001" match "ISO 27001 Certification Requirement".
_NOISE_SUFFIXES = (
    " certification", " compliance", " requirement", " requirements",
    " check", " verification", " policy", " standard", " standards",
    " insurance", " cover", " coverage",
)


def _normalize_name(name: str) -> str:
    """
    Lowercase + strip noise suffixes + collapse punctuation/whitespace.
    Used as the dedup key so 'ISO 27001' and 'ISO 27001 Certification'
    collapse to the same key and don't both survive into the setup.
    """
    n = name.lower().strip()
    for suffix in _NOISE_SUFFIXES:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


async def extract_criteria_from_user_sheet(sheet_bytes: bytes, filename: str) -> dict:
    """
    Parse a user-uploaded scoring sheet (CSV/Excel/PDF/DOCX) into the same
    shape as extract_criteria_from_rfp(): {"mandatory_checks": [...], "scoring_criteria": [...]}.

    Strategy:
    1. CSV/Excel  → try pandas column-name matching first (fast, free)
                  → if no scoring criteria found, fall back to LLM interpretation
    2. PDF/DOCX   → LLM interpretation directly
    Never raises — returns empty dict on any parse failure.
    """
    if not sheet_bytes:
        return {"mandatory_checks": [], "scoring_criteria": []}

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext in ("csv", "xlsx", "xls"):
            result = _parse_sheet_with_pandas(sheet_bytes, ext)
            # If pandas found no scoring criteria the column names didn't match —
            # fall back to LLM which can interpret any header format or language
            if not result.get("scoring_criteria"):
                print(f"  Sheet parser found no scoring criteria in '{filename}' — trying LLM fallback…")
                result = await _llm_interpret_sheet(sheet_bytes, ext)
            return result
        elif ext in ("pdf", "docx", "doc"):
            if ext == "pdf":
                text = extract_rfp_text(sheet_bytes)
            else:
                text = _extract_docx_text(sheet_bytes)
            return await extract_criteria_from_rfp(text)
        else:
            return {"mandatory_checks": [], "scoring_criteria": []}
    except Exception as e:
        print(f"User sheet extraction failed ({filename}): {e}")
        return {"mandatory_checks": [], "scoring_criteria": []}


async def _llm_interpret_sheet(sheet_bytes: bytes, ext: str) -> dict:
    """
    LLM fallback for scoring sheets with non-standard headers.
    Converts the sheet to plain text and asks the LLM to extract criteria.
    Works for any column naming convention, any industry, any language.
    """
    import io
    try:
        import pandas as pd
    except ImportError:
        return {"mandatory_checks": [], "scoring_criteria": []}

    try:
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(sheet_bytes))
        else:
            df = pd.read_excel(io.BytesIO(sheet_bytes))

        # Convert to plain readable text so the LLM can interpret any format
        sheet_text = df.to_string(index=False, na_rep="")
    except Exception as e:
        print(f"  LLM sheet fallback: could not read file — {e}")
        return {"mandatory_checks": [], "scoring_criteria": []}

    prompt = f"""You are reading a vendor evaluation scoring sheet uploaded by a procurement team.
The sheet may use any column names, any industry terminology, any language.

Your job: extract all evaluation criteria and return ONLY valid JSON in this exact shape:
{{
  "mandatory_checks": [
    {{
      "name": "short criterion name",
      "description": "what the vendor must provide",
      "what_passes": "what constitutes passing this check"
    }}
  ],
  "scoring_criteria": [
    {{
      "name": "criterion name",
      "weight": 0.35,
      "description": "what is being scored",
      "rubric_9_10": "evidence required for outstanding score",
      "rubric_6_8": "evidence required for good score",
      "rubric_3_5": "evidence required for adequate score",
      "rubric_0_2": "evidence required for poor score"
    }}
  ]
}}

Rules:
- mandatory_checks: rows marked MANDATORY, PASS/FAIL, required, obligatoire, or similar
- scoring_criteria: rows with a numeric weight or percentage
- weights must be decimals summing to 1.0 (convert percentages: 35% = 0.35)
- if rubric bands are not in the sheet, leave those fields as empty strings
- if no weight is stated but multiple scoring rows exist, distribute evenly
- return ONLY JSON — no prose, no markdown fences

SHEET CONTENT:
{sheet_text[:4000]}"""

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
        result = json.loads(clean.strip())

        # Normalise weights to 1.0
        scoring = result.get("scoring_criteria", [])
        if scoring:
            total = sum(float(c.get("weight", 0)) for c in scoring)
            if total > 0 and abs(total - 1.0) > 0.01:
                for c in scoring:
                    c["weight"] = round(float(c.get("weight", 0)) / total, 3)

        return result
    except Exception as e:
        print(f"  LLM sheet interpretation failed: {e}")
        return {"mandatory_checks": [], "scoring_criteria": []}


def _extract_docx_text(docx_bytes: bytes) -> str:
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(docx_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""


def _parse_sheet_with_pandas(sheet_bytes: bytes, ext: str) -> dict:
    """
    Parse CSV/Excel scoring sheet.
    Columns (case-insensitive): name, type/check_type, weight, description,
    what_passes, rubric_9_10, rubric_6_8, rubric_3_5, rubric_0_2.
    Rows with a numeric weight → scoring criteria; others → mandatory checks.
    """
    import io
    try:
        import pandas as pd
    except ImportError:
        return {"mandatory_checks": [], "scoring_criteria": []}

    if ext == "csv":
        df = pd.read_csv(io.BytesIO(sheet_bytes))
    else:
        df = pd.read_excel(io.BytesIO(sheet_bytes))

    # Normalise column names
    df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]

    def _col(preferred: list[str]) -> str | None:
        for c in preferred:
            if c in df.columns:
                return c
        return None

    name_col   = _col(["name", "criterion", "check_name", "criteria_name"])
    type_col   = _col(["check_type", "type", "kind"])
    weight_col = _col(["weight", "score_weight", "scoring_weight"])
    desc_col   = _col(["description", "desc", "detail"])
    pass_col   = _col(["what_passes", "pass_criteria", "passing"])

    if not name_col:
        return {"mandatory_checks": [], "scoring_criteria": []}

    mandatory_checks: list[dict] = []
    scoring_criteria: list[dict] = []

    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name or name.lower() == "nan":
            continue

        weight_raw = row.get(weight_col) if weight_col else None
        try:
            weight = float(weight_raw) if weight_raw is not None and str(weight_raw) != "nan" else None
        except (ValueError, TypeError):
            weight = None

        # Treat as scoring if: weight column exists AND value is a number
        # OR type column says "scoring"
        check_type = str(row.get(type_col, "")).lower().strip() if type_col else ""
        is_scoring = (weight is not None) or ("scor" in check_type)

        desc = str(row.get(desc_col, "")).strip() if desc_col else ""
        if desc == "nan":
            desc = ""
        what_passes = str(row.get(pass_col, "")).strip() if pass_col else ""
        if what_passes == "nan":
            what_passes = ""

        if is_scoring:
            scoring_criteria.append({
                "name": name,
                "weight": weight if weight is not None else 0.0,
                "description": desc,
                "rubric_9_10": str(row.get("rubric_9_10", "")).strip() or "",
                "rubric_6_8":  str(row.get("rubric_6_8",  "")).strip() or "",
                "rubric_3_5":  str(row.get("rubric_3_5",  "")).strip() or "",
                "rubric_0_2":  str(row.get("rubric_0_2",  "")).strip() or "",
            })
        else:
            mandatory_checks.append({
                "name": name,
                "description": desc,
                "what_passes": what_passes,
            })

    # Normalise scoring weights to 1.0 if any exist
    if scoring_criteria:
        total = sum(c["weight"] for c in scoring_criteria)
        if total > 0 and abs(total - 1.0) > 0.01:
            for c in scoring_criteria:
                c["weight"] = round(c["weight"] / total, 3)

    return {"mandatory_checks": mandatory_checks, "scoring_criteria": scoring_criteria}


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
            AND LOWER(department) = LOWER(:department)
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
    user_criteria: dict | None = None,
) -> dict:
    """
    Merges four sources. Priority: org > dept > user > rfp.
    Deduplicates by name (case-insensitive, noise-stripped).
    Each criterion gets a source field: org|dept|user|rfp.
    Returns dict compatible with EvaluationSetup model.
    """
    mandatory_checks = []
    scoring_criteria = []
    mandatory_names = set()
    scoring_names = set()

    # 1. Org criteria (highest priority, may be locked)
    for c in org_criteria:
        name_key = _normalize_name(c["name"])
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
        name_key = _normalize_name(c["name"])
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

    # 3. User-uploaded criteria (override RFP but not org/dept)
    for c in (user_criteria or {}).get("mandatory_checks", []):
        name_key = _normalize_name(c["name"])
        if name_key not in mandatory_names:
            uc_id = str(uuid.uuid4())[:8].upper()
            mandatory_checks.append({
                "check_id": f"MC-USER-{uc_id}",
                "name": c["name"],
                "description": c.get("description", ""),
                "what_passes": c.get("what_passes", ""),
                "extraction_target_id": f"ET-USER-{uc_id}",
                "source": "user",
                "is_locked": False,
            })
            mandatory_names.add(name_key)

    for c in (user_criteria or {}).get("scoring_criteria", []):
        name_key = _normalize_name(c["name"])
        if name_key not in scoring_names:
            uc_id = str(uuid.uuid4())[:8].upper()
            scoring_criteria.append({
                "criterion_id": f"SC-USER-{uc_id}",
                "name": c["name"],
                "weight": float(c.get("weight", 0.0)),
                "rubric_9_10": c.get("rubric_9_10", ""),
                "rubric_6_8":  c.get("rubric_6_8",  ""),
                "rubric_3_5":  c.get("rubric_3_5",  ""),
                "rubric_0_2":  c.get("rubric_0_2",  ""),
                "extraction_target_ids": [],
                "source": "user",
                "is_locked": False,
            })
            scoring_names.add(name_key)

    # 4. RFP-extracted criteria (skip duplicates against org + dept + user)
    for c in rfp_criteria.get("mandatory_checks", []):
        name_key = _normalize_name(c["name"])
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
        name_key = _normalize_name(c["name"])
        if name_key not in scoring_names:
            sc_id = str(uuid.uuid4())[:8].upper()  # noqa: F841 (reused var name is fine)
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

    # 5. Score guide enrichment pass
    # For any merged criterion with blank score guide bands, copy them from the RFP
    # if the RFP extracted the same criterion with scoring bands.
    # This covers: CSV has criterion + weight but no score guide; RFP has the guide.
    rfp_scoring_by_name = {
        _normalize_name(c["name"]): c
        for c in rfp_criteria.get("scoring_criteria", [])
    }
    for sc in scoring_criteria:
        name_key = _normalize_name(sc["name"])
        rfp_match = rfp_scoring_by_name.get(name_key)
        if not rfp_match:
            continue
        # Only fill in bands that are currently blank
        for band in ("rubric_9_10", "rubric_6_8", "rubric_3_5", "rubric_0_2"):
            if not sc.get(band) and rfp_match.get(band):
                sc[band] = rfp_match[band]
                sc["score_guide_source"] = "rfp"  # audit trail

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
