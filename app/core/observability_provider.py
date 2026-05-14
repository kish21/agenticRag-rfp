"""
Observability provider abstraction.
Mirrors llm_provider.py pattern — swap backends via OBSERVABILITY_PROVIDER in .env.

Supported providers:
  langfuse  — LangFuse cloud (default)
  stdout    — JSON logs to console (dev / air-gapped deployments)
  none      — silent drop (testing, CI)
"""
import json
from app.config import settings


def log_evaluation_run(
    run_id: str,
    agent_name: str,
    input_data: dict,
    output_data: dict,
    critic_verdict: str,
    latency_ms: int,
    org_id: str,
) -> None:
    provider = settings.observability_provider.lower()

    if provider == "langfuse":
        _langfuse_log_run(run_id, agent_name, input_data, output_data,
                          critic_verdict, latency_ms, org_id)
    elif provider == "stdout":
        _stdout_log("evaluation_run", {
            "run_id": run_id, "agent": agent_name,
            "critic_verdict": critic_verdict, "latency_ms": latency_ms,
            "org_id": org_id,
        })
    # none: drop silently


def log_critic_flag(
    run_id: str,
    flag_severity: str,
    flag_check: str,
    agent: str,
    org_id: str,
) -> None:
    provider = settings.observability_provider.lower()

    if provider == "langfuse":
        _langfuse_log_flag(run_id, flag_severity, flag_check, agent, org_id)
    elif provider == "stdout":
        _stdout_log("critic_flag", {
            "run_id": run_id, "severity": flag_severity,
            "check": flag_check, "agent": agent, "org_id": org_id,
        })
    # none: drop silently


# ── LangFuse backend ──────────────────────────────────────────────────────────

def _langfuse_log_run(
    run_id: str,
    agent_name: str,
    input_data: dict,
    output_data: dict,
    critic_verdict: str,
    latency_ms: int,
    org_id: str,
) -> None:
    try:
        from langfuse import Langfuse
        lf = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        with lf.start_as_current_observation(
            name=f"{agent_name}_run",
            type="CHAIN",
            metadata={
                "org_id": org_id,
                "critic_verdict": critic_verdict,
                "latency_ms": latency_ms,
            },
            input=input_data,
            output=output_data,
            trace_id=run_id,
        ):
            pass
        lf.flush()
    except Exception as e:
        print(f"[observability] LangFuse log_evaluation_run failed: {e}")


def _langfuse_log_flag(
    run_id: str,
    flag_severity: str,
    flag_check: str,
    agent: str,
    org_id: str,
) -> None:
    try:
        from langfuse import Langfuse
        lf = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        lf.create_score(
            name=f"critic_flag_{flag_severity}",
            trace_id=run_id,
            value=1.0,
            comment=f"{agent}: {flag_check}",
        )
        lf.flush()
    except Exception as e:
        print(f"[observability] LangFuse log_critic_flag failed: {e}")


# ── Stdout backend ────────────────────────────────────────────────────────────

def _stdout_log(event_type: str, data: dict) -> None:
    import datetime
    print(json.dumps({
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "event": event_type,
        **data,
    }))
