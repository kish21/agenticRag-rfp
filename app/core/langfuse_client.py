from langfuse import Langfuse
from app.config import settings

_lf: Langfuse | None = None


def get_langfuse() -> Langfuse:
    global _lf
    if _lf is None:
        _lf = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    return _lf


def log_evaluation_run(
    run_id: str,
    agent_name: str,
    input_data: dict,
    output_data: dict,
    critic_verdict: str,
    latency_ms: int,
    org_id: str,
) -> None:
    """Log an agent run as a LangFuse trace (v4 SDK)."""
    lf = get_langfuse()
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


def log_critic_flag(
    run_id: str,
    flag_severity: str,
    flag_check: str,
    agent: str,
    org_id: str,
) -> None:
    """Track critic flag rates over time. Alert if hard_flag_rate > 5%."""
    lf = get_langfuse()
    lf.create_score(
        name=f"critic_flag_{flag_severity}",
        trace_id=run_id,
        value=1.0,
        comment=f"{agent}: {flag_check}",
    )
    lf.flush()
