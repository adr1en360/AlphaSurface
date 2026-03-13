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
import uuid


@dataclass
class AgentTask:
    agent: str          # "research" | "youtube" | "image_gen" | "super_think" | "continuation"
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


# ── Scratch pad (deferred tasks for the continuation agent) ───────────────────
# The live model writes here when interrupted mid-task. A background
# non-live agent picks up each entry and executes the canvas instruction.

_MAX_SCRATCH_PAD = 20

@dataclass
class DeferredTask:
    task_id: str
    instruction: str
    status: str = "queued"   # queued | running | done | failed
    added_at: float = field(default_factory=time.time)
    finished_at: float | None = None

_scratch_pad: list[DeferredTask] = []


def add_deferred_task(instruction: str) -> str:
    """Queue a canvas instruction for the continuation agent. Returns task ID."""
    task_id = uuid.uuid4().hex[:8]
    _scratch_pad.append(DeferredTask(task_id=task_id, instruction=instruction))
    if len(_scratch_pad) > _MAX_SCRATCH_PAD:
        del _scratch_pad[:-_MAX_SCRATCH_PAD]
    dispatch("continuation", {"task_id": task_id, "instruction": instruction}, source="live_agent")
    return task_id


def mark_deferred_task(task_id: str, status: str) -> None:
    """Update task status after continuation agent finishes or fails."""
    for t in _scratch_pad:
        if t.task_id == task_id:
            t.status = status
            if status in ("done", "failed"):
                t.finished_at = time.time()
            break


def get_deferred_status_summary() -> str:
    """Compact human-readable status the live model can read back."""
    if not _scratch_pad:
        return "no deferred tasks"
    queued_tasks = [t for t in _scratch_pad if t.status == "queued"]
    running_tasks = [t for t in _scratch_pad if t.status == "running"]
    failed_tasks = [t for t in _scratch_pad if t.status == "failed"]
    done_tasks = [t for t in _scratch_pad if t.status == "done"]

    queued = len(queued_tasks)
    running = len(running_tasks)
    failed = len(failed_tasks)
    parts = []
    if queued:  parts.append(f"{queued} queued")
    if running: parts.append(f"{running} running")
    if failed:  parts.append(f"{failed} failed")
    summary = ", ".join(parts) if parts else "all done"
    if queued_tasks:
        summary += " | queued_ids=" + ",".join(t.task_id for t in queued_tasks[-3:])
    if running_tasks:
        summary += " | running_ids=" + ",".join(t.task_id for t in running_tasks[-3:])
    if done_tasks:
        recent = "; ".join(f"{t.task_id}:{t.instruction[:40]}" for t in done_tasks[-3:])
        summary += f" | completed: {recent}"
    return summary
