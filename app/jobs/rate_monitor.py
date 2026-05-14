import datetime
import httpx

from app.core.observability_provider import log_critic_flag

_ALERT_THRESHOLD_PCT = 2.0
_LOOKBACK_HOURS = 1


async def check_rate_limit_health(
    langfuse_project_url: str | None = None,
) -> dict:
    """
    Checks if OpenAI rate-limit errors occurred in the last hour.
    Alerts via LangFuse if error rate > 2%.
    Run every 30 minutes via Modal scheduled function.
    """
    now = datetime.datetime.utcnow()
    window_start = now - datetime.timedelta(hours=_LOOKBACK_HOURS)

    # Read rate-limit counters from the in-process rate limiter state
    from app.core.rate_limiter import RateLimiter  # lazy import — avoids circular

    rl: RateLimiter = RateLimiter.get_instance()
    total_calls: int = rl.get_call_count(since=window_start)
    rate_limit_errors: int = rl.get_error_count(since=window_start, status=429)

    error_pct = (rate_limit_errors / total_calls * 100) if total_calls > 0 else 0.0
    alert_triggered = error_pct > _ALERT_THRESHOLD_PCT

    if alert_triggered:
        monitor_run_id = f"rate_monitor_{now.strftime('%Y%m%d_%H%M')}"
        log_critic_flag(
            run_id=monitor_run_id,
            flag_severity="hard",
            flag_check=f"rate_limit_error_rate={error_pct:.1f}% > {_ALERT_THRESHOLD_PCT}%",
            agent="rate_monitor",
            org_id="platform",
        )

    return {
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "total_calls": total_calls,
        "rate_limit_errors": rate_limit_errors,
        "error_pct": round(error_pct, 2),
        "alert_triggered": alert_triggered,
    }


async def _post_slack_alert(webhook_url: str, message: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(webhook_url, json={"text": message})
