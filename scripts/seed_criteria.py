import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import uuid, json
from app.db.fact_store import get_engine
import sqlalchemy as sa

# Dev org — the only org that exists in the local dev database
ORG_ID = "00000000-0000-0000-0000-000000000001"

def seed():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(sa.text(
            "SET LOCAL app.current_org_id = :oid"
        ), {"oid": ORG_ID})

        # Clear old test data
        conn.execute(sa.text(
            "DELETE FROM org_criteria_templates "
            "WHERE org_id::text = :oid"
        ), {"oid": ORG_ID})
        conn.execute(sa.text(
            "DELETE FROM dept_criteria_templates "
            "WHERE org_id::text = :oid"
        ), {"oid": ORG_ID})

        # Org mandatory — locked, apply to all evaluations
        org_checks = [
            ("ISO 27001 Certification",
             "Current valid ISO 27001 from accredited body",
             "Certificate number, issuing body, valid-until date present",
             True),
            ("Professional Indemnity minimum £5M",
             "PI insurance at least £5,000,000 per claim",
             "Named provider and £5M+ amount explicitly stated",
             True),
        ]
        for name, desc, passes, locked in org_checks:
            conn.execute(sa.text("""
                INSERT INTO org_criteria_templates
                (template_id, org_id, check_type, name,
                 description, what_passes, is_locked, created_by)
                VALUES (:tid, CAST(:oid AS uuid), 'mandatory',
                 :name, :desc, :passes, :locked, 'seed')
            """), {
                "tid": str(uuid.uuid4()),
                "oid": ORG_ID,
                "name": name, "desc": desc,
                "passes": passes, "locked": locked,
            })

        # Dept criteria for procurement
        dept_items = [
            ("mandatory", "EU or UK Based Service Desk",
             "Primary desk in EU or UK, no offshore",
             "City and country explicitly stated as EU or UK",
             0.0, {}, False),
            ("scoring", "Relevant Experience", "", "",
             0.35, {
               "9_10": "3+ named comparable projects with outcomes",
               "6_8":  "1-2 comparable projects",
               "3_5":  "Some experience, limited specifics",
               "0_2":  "No comparable experience",
             }, False),
            ("scoring", "Service Level Commitments", "", "",
             0.30, {
               "9_10": "P1 <=15min response, <=4h resolution, 99.95% uptime",
               "6_8":  "P1 <=30min, <=8h, 99.9% uptime",
               "3_5":  "SLAs present but below expectations",
               "0_2":  "No SLAs provided",
             }, False),
        ]
        for check_type, name, desc, passes, weight, rubric, locked \
                in dept_items:
            conn.execute(sa.text("""
                INSERT INTO dept_criteria_templates
                (template_id, org_id, department, check_type,
                 name, description, what_passes, default_weight,
                 rubric, is_locked, created_by)
                VALUES (:tid, CAST(:oid AS uuid), 'procurement',
                 :ct, :name, :desc, :passes, :weight,
                 CAST(:rubric AS jsonb), :locked, 'seed')
            """), {
                "tid": str(uuid.uuid4()), "oid": ORG_ID,
                "ct": check_type, "name": name,
                "desc": desc, "passes": passes,
                "weight": weight,
                "rubric": json.dumps(rubric),
                "locked": locked,
            })

        conn.commit()
        print("Seeded: 2 org mandatory checks (locked)")
        print("Seeded: 1 dept mandatory + 2 dept scoring criteria")
        print(f"Org ID: {ORG_ID}")

    # Seed org_settings using the product.yaml balanced preset
    from app.core.org_settings import upsert_org_settings
    upsert_org_settings(ORG_ID, updated_by="seed")
    print(f"Seeded: org_settings for {ORG_ID} (balanced preset)")

seed()
