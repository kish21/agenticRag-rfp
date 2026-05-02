from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.agent_registry import register_agent, get_agent_config, list_agents
from app.core.dependencies import get_current_user
from app.core.auth import require_role, TokenData

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class RegisterAgentRequest(BaseModel):
    config: dict


class RegisterAgentResponse(BaseModel):
    agent_id: str
    message: str


@router.post("/agents", response_model=RegisterAgentResponse)
async def register_new_agent(
    body: RegisterAgentRequest,
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin")),
):
    """Register a new agent config for the caller's org. One API call — zero code changes."""
    try:
        agent_id = register_agent(org_id=user.org_id, config=body.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return RegisterAgentResponse(agent_id=agent_id, message="Agent registered successfully")


@router.get("/agents")
async def list_org_agents(
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin", "department_admin")),
):
    """List all active agents for the caller's org."""
    return {"agents": list_agents(org_id=user.org_id)}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    user: TokenData = Depends(get_current_user),
):
    """Retrieve the config for a specific agent."""
    config = get_agent_config(agent_id=agent_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent_id": agent_id, "config": config}
