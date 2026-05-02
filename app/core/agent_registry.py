import uuid
import sqlalchemy as sa
from app.db.fact_store import get_engine


def register_agent(org_id: str, config: dict) -> str:
    """
    Persists an AgentConfig to the agent_registry table.
    Returns the generated agent_id (UUID string).
    """
    identity = config.get("identity", {})
    agent_id = str(uuid.uuid4())
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO agent_registry
                    (agent_id, org_id, agent_name, agent_type, config)
                VALUES
                    (:agent_id, :org_id::uuid, :agent_name, :agent_type, :config::jsonb)
                ON CONFLICT (agent_id) DO NOTHING
            """),
            {
                "agent_id": agent_id,
                "org_id": org_id,
                "agent_name": identity.get("agent_name", "unnamed"),
                "agent_type": identity.get("agent_type", "custom"),
                "config": sa.func.cast(
                    __import__("json").dumps(config), sa.Text
                ),
            },
        )
        conn.commit()
    return agent_id


def get_agent_config(agent_id: str) -> dict | None:
    """Returns the config JSON for the given agent_id, or None if not found."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT config FROM agent_registry WHERE agent_id = :aid AND is_active = true"
            ),
            {"aid": agent_id},
        ).fetchone()
    return dict(row.config) if row else None


def list_agents(org_id: str) -> list[dict]:
    """Returns all active agents for an org."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT agent_id, agent_name, agent_type, created_at "
                "FROM agent_registry "
                "WHERE org_id = :org_id::uuid AND is_active = true "
                "ORDER BY created_at DESC"
            ),
            {"org_id": org_id},
        ).fetchall()
    return [
        {
            "agent_id": str(r.agent_id),
            "agent_name": r.agent_name,
            "agent_type": r.agent_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
