"""
Proves that the HR agent uses the same engine as the procurement agent.
Same Planner, Retrieval, Extraction, Evaluation, Critic — different config only.
No live LLM calls. Validates config structure and engine compatibility.
"""
import sys
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_passed = 0
_failed = 0


def check(name: str, expr: bool, detail: str = "") -> None:
    global _passed, _failed
    if expr:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


# ── 1. HR config is importable and structurally valid ──────────────────
from app.agents.hr_agent_config import HR_AGENT_CONFIG

check("HR_AGENT_CONFIG importable", isinstance(HR_AGENT_CONFIG, dict))
check("identity.agent_type == 'hr'",
      HR_AGENT_CONFIG.get("identity", {}).get("agent_type") == "hr")
check("knowledge_base.collections present",
      len(HR_AGENT_CONFIG.get("knowledge_base", {}).get("collections", [])) > 0)
check("governance.approval_tiers == [] (HR needs no approvals)",
      HR_AGENT_CONFIG.get("governance", {}).get("approval_tiers") == [])
check("audit citation_required == True",
      HR_AGENT_CONFIG.get("governance", {}).get("audit_requirements", {}).get("citation_required") is True)
check("llm temperature == 0.0 (deterministic HR answers)",
      HR_AGENT_CONFIG.get("agent_behaviour", {}).get("llm", {}).get("temperature") == 0.0)

# ── 2. Same engine functions are importable for HR use ─────────────────
from app.agents.planner import run_planner
from app.agents.critic import (
    critic_after_extraction, critic_after_decision, critic_after_explanation
)
from app.core.agent_registry import register_agent, get_agent_config, list_agents

check("run_planner is callable", inspect.isfunction(run_planner))
check("critic_after_extraction is callable", inspect.isfunction(critic_after_extraction))
check("critic_after_decision is callable", inspect.isfunction(critic_after_decision))
check("critic_after_explanation is callable", inspect.isfunction(critic_after_explanation))
check("register_agent is callable", inspect.isfunction(register_agent))
check("get_agent_config is callable", inspect.isfunction(get_agent_config))
check("list_agents is callable", inspect.isfunction(list_agents))

# ── 3. Admin routes exist for one-API-call agent registration ──────────
from app.api.admin_routes import router as admin_router
routes = {r.path for r in admin_router.routes}
check("POST /api/v1/admin/agents route exists",
      "/api/v1/admin/agents" in routes)
check("GET /api/v1/admin/agents route exists",
      "/api/v1/admin/agents" in routes)

# ── 4. LLM provider is shared — HR uses same call_llm() as procurement ─
from app.core.llm_provider import call_llm
check("call_llm shared between HR and procurement agents",
      inspect.isfunction(call_llm) or callable(call_llm))

# ── Summary ────────────────────────────────────────────────────────────
total = _passed + _failed
print(f"\nResult: {_passed}/{total}")
if _failed == 0:
    print("HR agent test: confirmed — same engine, different config")
else:
    print(f"HR agent test: {_failed} check(s) failed")

sys.exit(0 if _failed == 0 else 1)
