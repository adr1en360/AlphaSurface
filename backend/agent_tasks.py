"""
AlphaSurface — Shared agent task queue.

This is the single coordination point between the Live Agent and sub-agents.

Flow A (Live Agent dispatches):
    User says "research X" → Live Agent calls dispatch_research("X")
    → job lands in agent_task_queue
    → ResearchAgent listener picks it up
    → bus.signal_agent_acted() prevents event bus from double-firing

Flow B (event bus fires independently):
    canvas_idle + audio_silent → bus publishes "research_ready"
    → ResearchAgent._on_research_ready() creates a job
    → same job lands in agent_task_queue
    → same ResearchAgent listener picks it up

One queue. One listener per agent. Two entry points. No duplication.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any
import time


@dataclass
class AgentTask:
    agent: str          # "research" | "youtube" | "image_gen" | "super_think" | "provocation"
    payload: dict       # agent-specific data e.g. {"query": "Nigeria GDP"}
    source: str         # "live_agent" | "event_bus" — for logging
    priority: int = 1   # lower = higher priority (reserved for future use)


# ── Singleton queue ───────────────────────────────────────────────────────────

_task_queue: asyncio.Queue[AgentTask] | None = None
_task_board: dict[str, Any] = {
    "queued": {},
    "running": {},
    "last_events": [],
}


def _inc(bucket: str, agent: str, delta: int = 1) -> None:
    current = int(_task_board[bucket].get(agent, 0)) + delta
    _task_board[bucket][agent] = max(0, current)


def _push_event(kind: str, agent: str, source: str, payload: dict | None = None) -> None:
    events = _task_board["last_events"]
    events.append({
        "ts": time.time(),
        "kind": kind,
        "agent": agent,
        "source": source,
        "payload": payload or {},
    })
    if len(events) > 20:
        del events[:-20]


def note_started(agent: str, source: str, payload: dict | None = None) -> None:
    _inc("queued", agent, -1)
    _inc("running", agent, 1)
    _push_event("started", agent, source, payload)


def note_finished(agent: str, source: str, payload: dict | None = None, status: str = "done") -> None:
    _inc("running", agent, -1)
    _push_event(status, agent, source, payload)


def get_task_board_snapshot() -> dict[str, Any]:
    return {
        "queued": dict(_task_board["queued"]),
        "running": dict(_task_board["running"]),
        "last_events": list(_task_board["last_events"]),
    }


def format_task_board() -> str:
    snap = get_task_board_snapshot()
    queued_total = sum(int(v) for v in snap["queued"].values())
    running_total = sum(int(v) for v in snap["running"].values())
    running_agents = ", ".join(
        f"{k}:{v}" for k, v in sorted(snap["running"].items()) if int(v) > 0
    ) or "none"
    queued_agents = ", ".join(
        f"{k}:{v}" for k, v in sorted(snap["queued"].items()) if int(v) > 0
    ) or "none"
    return (
        f"task board -> running={running_total} [{running_agents}] ; "
        f"queued={queued_total} [{queued_agents}]"
    )


def get_task_queue() -> asyncio.Queue[AgentTask]:
    global _task_queue
    if _task_queue is None:
        _task_queue = asyncio.Queue()
    return _task_queue


def dispatch(agent: str, payload: dict, source: str = "live_agent") -> None:
    """
    Put a task on the queue. Synchronous — safe to call from ADK tool context.
    Sub-agent listener loops pick this up.
    """
    task = AgentTask(agent=agent, payload=payload, source=source)
    try:
        get_task_queue().put_nowait(task)
        _inc("queued", agent, 1)
        _push_event("queued", agent, source, payload)
        print(f"[TaskQueue] {source} → {agent}: {payload}")
    except asyncio.QueueFull:
        print(f"[TaskQueue] Queue full — dropped {agent} task")
