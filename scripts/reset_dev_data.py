"""
scripts/reset_dev_data.py

Wipes all dummy data from PostgreSQL and Qdrant, then re-seeds criteria templates.
Leaves Docker running — no schema re-apply needed.

Usage:
    python scripts/reset_dev_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import sqlalchemy as sa
from app.db.fact_store import get_engine
from app.core.qdrant_client import get_qdrant_client


TABLES_TO_TRUNCATE = [
    # Evaluation run data only — in dependency order (children before parents)
    # KEPT: users, tenant_billing, tenant_modules, org_settings, org_settings_audit,
    #        org_criteria_templates, dept_criteria_templates, agent_registry
    "retrieval_log",
    "audit_overrides",
    "approvals",
    "audit_log",
    "decisions",
    "extracted_facts",
    "extracted_pricing",
    "extracted_projects",
    "extracted_slas",
    "extracted_insurance",
    "extracted_certifications",
    "vendor_documents",
    "evaluation_runs",
    "evaluation_setups",
]


def reset_postgres():
    print("── PostgreSQL ──────────────────────────────────")
    engine = get_engine()
    with engine.begin() as conn:
        # Disable RLS session var requirement for admin reset
        conn.execute(sa.text("SET session_replication_role = replica"))

        for table in TABLES_TO_TRUNCATE:
            try:
                conn.execute(sa.text(f"TRUNCATE {table} CASCADE"))
                print(f"  ✓ truncated {table}")
            except Exception as e:
                print(f"  ! skipped {table}: {e}")

        conn.execute(sa.text("SET session_replication_role = DEFAULT"))

    print("  PostgreSQL reset complete.\n")


def reset_qdrant():
    print("── Qdrant ──────────────────────────────────────")
    client = get_qdrant_client()
    collections = client.get_collections().collections

    if not collections:
        print("  No collections found — nothing to delete.\n")
        return

    for col in collections:
        client.delete_collection(col.name)
        print(f"  ✓ deleted collection: {col.name}")

    print("  Qdrant reset complete.\n")


def reseed():
    print("── Re-seeding criteria templates ───────────────")
    import importlib.util
    seed_path = os.path.join(os.path.dirname(__file__), "seed_criteria.py")
    spec = importlib.util.spec_from_file_location("seed_criteria", seed_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.seed()
    print("  Seed complete.\n")


if __name__ == "__main__":
    print("\nDev data reset starting...\n")
    reset_postgres()
    reset_qdrant()
    print("Done. Evaluation run data cleared. Users, orgs, criteria templates preserved.")
