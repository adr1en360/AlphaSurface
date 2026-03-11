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


@dataclass
class AgentTask:
    agent: str          # "research" | "youtube" | "image_gen" | "super_think" | "provocation"
    payload: dict       # agent-specific data e.g. {"query": "Nigeria GDP"}
    source: str         # "live_agent" | "event_bus" — for logging
    priority: int = 1   # lower = higher priority (reserved for future use)


# ── Singleton queue ───────────────────────────────────────────────────────────

_task_queue: asyncio.Queue[AgentTask] | None = None


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
        print(f"[TaskQueue] {source} → {agent}: {payload}")
    except asyncio.QueueFull:
        print(f"[TaskQueue] Queue full — dropped {agent} task")
