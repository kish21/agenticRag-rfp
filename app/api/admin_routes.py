from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.domain.agent_registry import register_agent, get_agent_config, list_agents
from app.auth.dependencies import get_current_user
from app.auth.jwt import require_role, TokenData

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


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9 — Multi-user RFP visibility administration
# ═══════════════════════════════════════════════════════════════════════════
# Endpoints for admins to manage matrix department membership and approval
# assignments. These NEVER run autonomously; access lists are decided by
# humans and inherited by runs (see Phase 9 invariant).

from app.domain.visibility import (
    add_user_to_department as _add_user_to_dept,
    assign_approver as _assign_approver,
)


class UserDeptAssignment(BaseModel):
    user_id: str
    department_id: str
    role_in_dept: str = "member"   # 'member' | 'lead' | 'observer'


@router.post("/user-departments")
async def add_user_department(
    body: UserDeptAssignment,
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin", "department_admin")),
):
    """Grant a user membership in a department. Idempotent — re-adding with a
    different role updates the role_in_dept."""
    try:
        _add_user_to_dept(body.user_id, body.department_id, body.role_in_dept)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "user_id": body.user_id, "department_id": body.department_id}


class ApprovalAssignmentRequest(BaseModel):
    run_id: str
    approver_user_id: str
    approver_role: str  # 'cfo' | 'cto' | 'cpo' | 'legal' | etc.


@router.post("/approval-assignments")
async def add_approval_assignment(
    body: ApprovalAssignmentRequest,
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin", "department_admin")),
):
    """Assign an approver to an evaluation_run. Re-assigning the same user
    resets status to 'pending'."""
    try:
        _assign_approver(body.run_id, body.approver_user_id, body.approver_role)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "run_id": body.run_id, "approver_user_id": body.approver_user_id}
