import datetime
import httpx
import sqlalchemy as sa

from app.providers.observability import log_critic_flag

_ALERT_THRESHOLD_PCT = 2.0
_LOOKBACK_HOURS = 1


async def check_rate_limit_health(
    langfuse_project_url: str | None = None,
) -> dict:
    """
    Checks if OpenAI rate-limit errors occurred in the last hour.
    Alerts via LangFuse if error rate > 2%.
    Run every 30 minutes via Modal scheduled function.

    Reads from the shared `rate_limit_stats` table (written by the API workers'
    rate limiter when RATE_METRICS_ENABLED=true), NOT in-process counters — the
    monitor runs in a different process than the workers, so in-memory state is
    always empty here.
    """
    now = datetime.datetime.utcnow()
    window_start = now - datetime.timedelta(hours=_LOOKBACK_HOURS)

    from app.db.fact_store import get_admin_engine  # lazy import — avoids circular

    total_calls = 0
    rate_limit_errors = 0
    try:
        # System cron with no org context — admin engine (RLS-exempt).
        with get_admin_engine().connect() as conn:
            row = conn.execute(
                sa.text(
                    """
                    SELECT COALESCE(SUM(total_calls), 0)        AS total_calls,
                           COALESCE(SUM(rate_limit_errors), 0)  AS rate_limit_errors
                    FROM rate_limit_stats
                    WHERE minute_bucket >= :since
                    """
                ),
                {"since": window_start},
            ).fetchone()
            if row is not None:
                total_calls = int(row.total_calls)
                rate_limit_errors = int(row.rate_limit_errors)
    except Exception as e:
        # No metrics table / DB unavailable — report a no-data result rather than
        # crashing the cron.
        return {
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "total_calls": 0,
            "rate_limit_errors": 0,
            "error_pct": 0.0,
            "alert_triggered": False,
            "no_data": True,
            "error": str(e),
        }

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
