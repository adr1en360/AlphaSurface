"""
AlphaSurface — Shared agent task queue.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any
import time
import uuid


@dataclass
class AgentTask:
    agent: str
    payload: dict
    source: str
    priority: int = 1


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
    task = AgentTask(agent=agent, payload=payload, source=source)
    try:
        get_task_queue().put_nowait(task)
        _inc("queued", agent, 1)
        _push_event("queued", agent, source, payload)
        print(f"[TaskQueue] {source} → {agent}: {payload}")
    except asyncio.QueueFull:
        print(f"[TaskQueue] Queue full — dropped {agent} task")


# ── Scratch pad ───────────────────────────────────────────────────────────────

_MAX_SCRATCH_PAD = 20

@dataclass
class DeferredTask:
    task_id: str
    instruction: str
    status: str = "queued"
    added_at: float = field(default_factory=time.time)
    finished_at: float | None = None

_scratch_pad: list[DeferredTask] = []


def add_deferred_task(instruction: str) -> str:
    task_id = uuid.uuid4().hex[:8]
    _scratch_pad.append(DeferredTask(task_id=task_id, instruction=instruction))
    if len(_scratch_pad) > _MAX_SCRATCH_PAD:
        del _scratch_pad[:-_MAX_SCRATCH_PAD]
    dispatch("continuation", {"task_id": task_id, "instruction": instruction}, source="live_agent")
    return task_id


def mark_deferred_task(task_id: str, status: str) -> None:
    for t in _scratch_pad:
        if t.task_id == task_id:
            t.status = status
            if status in ("done", "failed"):
                t.finished_at = time.time()
            break


def get_deferred_status_summary() -> str:
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


# ── Session reset ─────────────────────────────────────────────────────────────
# Call this at the start of each live session to clear transient state.

def reset_session_state() -> None:
    """
    Clear all per-session internal state:
    - Think log (agent reasoning scratchpad)
    - Todo list
    - Review queue
    Called by live_session.py at the start of each Gemini session.
    """
    try:
        from tools.agent_state import clear_think_log, clear_todos
        clear_think_log()
        clear_todos()
    except ImportError:
        pass

    # Clear scratch pad entries that are already done/failed
    global _scratch_pad
    _scratch_pad = [t for t in _scratch_pad if t.status in ("queued", "running")]
    print("[AgentTasks] Session state reset")
