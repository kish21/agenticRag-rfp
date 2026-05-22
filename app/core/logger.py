"""
app/core/logger.py

Dual logger for agenticRag-rfp.

  DevLogger   — full technical detail → dev JSONL file + Python logger + SSE broadcast
  AgentLogger — customer-facing progress → agent JSONL file + SSE broadcast

Both broadcast live to any connected frontend clients via asyncio queues.
LangFuse / LangSmith traces are handled separately by observability_provider.py.
"""

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


# ── Log levels ────────────────────────────────────────────────────────────────

class DevLevel(str, Enum):
    DEBUG   = "DEBUG"
    INFO    = "INFO"
    WARN    = "WARN"
    ERROR   = "ERROR"
    SUCCESS = "SUCCESS"
    AGENT   = "AGENT"
    RAG     = "RAG"
    LLM     = "LLM"
    CRITIC  = "CRITIC"


class AgentLevel(str, Enum):
    PROGRESS = "PROGRESS"
    SUCCESS  = "SUCCESS"
    WARNING  = "WARNING"
    ERROR    = "ERROR"


# ── Entry helpers ─────────────────────────────────────────────────────────────

def _dev_entry(level: DevLevel, agent: str, message: str,
               data: Optional[dict], run_id: Optional[str],
               org_id: Optional[str], elapsed_ms: Optional[int]) -> dict:
    return {
        "type":       "dev",
        "ts":         datetime.utcnow().isoformat() + "Z",
        "level":      level.value,
        "agent":      agent,
        "message":    message,
        "data":       data or {},
        "run_id":     run_id,
        "org_id":     org_id,
        "elapsed_ms": elapsed_ms,
    }


def _agent_entry(level: AgentLevel, agent: str, message: str,
                 run_id: Optional[str], org_id: Optional[str]) -> dict:
    steps = {
        "planner": 1, "ingestion": 2, "retrieval": 3,
        "extraction": 4, "evaluation": 5, "comparator": 6,
        "decision": 7, "explanation": 8, "critic": 9,
    }
    step  = steps.get(agent.lower(), 0)
    total = 9
    return {
        "type":    "agent",
        "ts":      datetime.utcnow().isoformat() + "Z",
        "level":   level.value,
        "agent":   agent,
        "message": message,
        "step":    step,
        "total":   total,
        "percent": int((step / total) * 100) if total else 0,
        "run_id":  run_id,
        "org_id":  org_id,
    }


# ── Main logger ───────────────────────────────────────────────────────────────

class RFPLogger:
    """
    Singleton. Import and use as:
        from app.core.logger import rfp_logger, DevLevel, AgentLevel
    """

    def __init__(self):
        self._dev_queue:   deque = deque(maxlen=2000)
        self._agent_queue: deque = deque(maxlen=500)
        self._sse_clients: list  = []
        self._run_starts:  dict  = {}
        self._setup_files()
        self._setup_python_logger()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_files(self):
        Path("logs").mkdir(exist_ok=True)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        self._dev_file   = Path(f"logs/dev_{today}.jsonl")
        self._agent_file = Path(f"logs/agent_{today}.jsonl")

    def _setup_python_logger(self):
        Path("logs").mkdir(exist_ok=True)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(f"logs/platform_{today}.log", encoding="utf-8"),
            ],
        )
        self._py = logging.getLogger("agenticRag-rfp")

    # ── SSE pub/sub ───────────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._sse_clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        try:
            self._sse_clients.remove(q)
        except ValueError:
            pass

    def _broadcast(self, entry: dict):
        dead = []
        for q in self._sse_clients:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            try:
                self._sse_clients.remove(q)
            except ValueError:
                pass

    def _write_jsonl(self, path: Path, entry: dict):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    # ── Pipeline lifecycle ────────────────────────────────────────────────────

    def start_run(self, run_id: str, org_id: str, rfp_id: str,
                  vendor_count: int, model: str = ""):
        self._run_starts[run_id] = time.monotonic()
        self.dev(DevLevel.AGENT, "Pipeline", "Evaluation started",
                 data={"rfp_id": rfp_id, "vendors": vendor_count, "model": model},
                 run_id=run_id, org_id=org_id)

    def end_run(self, run_id: str, org_id: str, status: str,
                recommended_vendor: Optional[str] = None):
        elapsed = round(time.monotonic() - self._run_starts.pop(run_id, time.monotonic()), 2)
        level = DevLevel.SUCCESS if status in ("complete", "completed") else DevLevel.ERROR
        self.dev(level, "Pipeline",
                 f"Evaluation {status} in {elapsed}s",
                 data={"elapsed_s": elapsed, "status": status,
                       "recommended": recommended_vendor},
                 run_id=run_id, org_id=org_id)

    # ── Developer log ─────────────────────────────────────────────────────────

    def dev(self, level: DevLevel, agent: str, message: str,
            data: Optional[dict] = None,
            run_id: Optional[str] = None, org_id: Optional[str] = None):
        elapsed_ms: Optional[int] = None
        if run_id and run_id in self._run_starts:
            elapsed_ms = round((time.monotonic() - self._run_starts[run_id]) * 1000)

        entry = _dev_entry(level, agent, message, data, run_id, org_id, elapsed_ms)
        self._dev_queue.append(entry)
        self._write_jsonl(self._dev_file, entry)
        self._broadcast(entry)

        # Mirror to Python logger
        py_level = {
            DevLevel.DEBUG: logging.DEBUG,   DevLevel.INFO: logging.INFO,
            DevLevel.WARN: logging.WARNING,  DevLevel.ERROR: logging.ERROR,
            DevLevel.SUCCESS: logging.INFO,  DevLevel.AGENT: logging.INFO,
            DevLevel.RAG: logging.DEBUG,     DevLevel.LLM: logging.DEBUG,
            DevLevel.CRITIC: logging.WARNING,
        }.get(level, logging.INFO)
        suffix = f" | {json.dumps(data)}" if data else ""
        self._py.log(py_level, f"[{agent}] {message}{suffix}")

    # ── Customer-facing agent log ─────────────────────────────────────────────

    def agent(self, level: AgentLevel, agent: str, message: str,
              run_id: Optional[str] = None, org_id: Optional[str] = None):
        entry = _agent_entry(level, agent, message, run_id, org_id)
        self._agent_queue.append(entry)
        self._write_jsonl(self._agent_file, entry)
        self._broadcast(entry)

    # ── History (replay on SSE connect) ──────────────────────────────────────

    def get_dev_history(self, run_id: Optional[str] = None,
                        org_id: Optional[str] = None, limit: int = 500) -> list:
        entries = list(self._dev_queue)
        if run_id:
            entries = [e for e in entries if e.get("run_id") == run_id]
        if org_id:
            entries = [e for e in entries if e.get("org_id") == org_id]
        return entries[-limit:]

    def get_agent_history(self, run_id: Optional[str] = None,
                          org_id: Optional[str] = None, limit: int = 200) -> list:
        entries = list(self._agent_queue)
        if run_id:
            entries = [e for e in entries if e.get("run_id") == run_id]
        if org_id:
            entries = [e for e in entries if e.get("org_id") == org_id]
        return entries[-limit:]


# ── Singleton ─────────────────────────────────────────────────────────────────
rfp_logger = RFPLogger()
