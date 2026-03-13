"""
AlphaSurface — Agent dispatcher.

Single loop. Reads from agent_task_queue. Routes to the right sub-agent.
Both Live Agent dispatches and event bus triggers land here.

Each sub-agent handler is registered by name. When a task arrives,
the dispatcher calls the right handler as an asyncio task (non-blocking).

To add a new agent: implement a handler, call register_handler().
"""

import asyncio
from typing import Callable, Awaitable

from agent_tasks import AgentTask, get_task_queue, note_started, note_finished
from event_bus import get_event_bus

# Type for agent handler functions
AgentHandler = Callable[[dict], Awaitable[None]]

_handlers: dict[str, AgentHandler] = {}


def register_handler(agent_name: str, handler: AgentHandler) -> None:
    """Register an async handler for a named agent."""
    _handlers[agent_name] = handler
    print(f"[Dispatcher] Registered handler: {agent_name}")


async def run_dispatcher() -> None:
    """
    Main dispatch loop. Run as a background task at app startup.
    Reads AgentTask objects from the shared queue and routes them.
    """
    queue = get_task_queue()
    print("[Dispatcher] Running")

    while True:
        try:
            task: AgentTask = await queue.get()

            handler = _handlers.get(task.agent)
            if handler is None:
                print(f"[Dispatcher] No handler for agent '{task.agent}' — task dropped")
                continue

            print(f"[Dispatcher] Routing {task.agent} task (source={task.source})")

            # Fire handler as independent task — dispatcher keeps running immediately
            asyncio.create_task(_run_handler(task, handler))

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Dispatcher] Error: {e}")
            await asyncio.sleep(0.1)


async def _run_handler(task: AgentTask, handler: AgentHandler) -> None:
    """Wraps handler execution with error isolation and cooldown signalling."""
    bus = get_event_bus()
    note_started(task.agent, task.source, task.payload)
    try:
        bus.signal_agent_acted()  # block event bus from double-firing
        await handler(task.payload)
        note_finished(task.agent, task.source, task.payload, status="done")
    except Exception as e:
        note_finished(task.agent, task.source, task.payload, status="failed")
        print(f"[Dispatcher] Handler '{task.agent}' failed: {e}")
        import traceback
        traceback.print_exc()
