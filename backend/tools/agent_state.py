"""
tools/agent_state.py — Agent internal state tools

These tools manage the agent's internal working memory.
NOTHING here touches the canvas. All state is in-process only.

Three tools:
  think(reasoning)     — write a reasoning note to scratchpad before acting
  todo_update(...)     — add/complete/list tasks the agent is tracking
  review_area(...)     — schedule a follow-up pass to review a canvas region
"""

import time
import uuid
from typing import Literal


# ── Scratchpad (think) ────────────────────────────────────────────────────────
# In-memory only. Never sent to canvas. Cleared each session restart.

_think_log: list[dict] = []
_MAX_THINK_LOG = 50


def think(reasoning: str) -> str:
    """
    Write a reasoning note to your internal scratchpad BEFORE taking a canvas action.
    Use this when:
    - You are about to make a placement decision and want to reason through it
    - You are deciding which tool to call next
    - You want to note something about the canvas state without saying it aloud
    - You want to plan a multi-step sequence before executing it

    This does NOT appear on the canvas. It is purely internal.
    The user cannot see this. Do not use it to communicate with the user.

    Examples:
      think("Canvas has 4 shapes in top-left. User is building a flow diagram.
             I should place the next node to the right of the last geo shape.")

      think("User asked for water cycle diagram. Plan:
             1. place Evaporation geo at center
             2. place Condensation above it
             3. place Precipitation to the right
             4. place Collection below
             5. bind arrows in sequence
             6. dispatch_image_gen for illustration")

    Returns: confirmation that the thought was logged.
    """
    entry = {
        "id": uuid.uuid4().hex[:8],
        "ts": time.time(),
        "reasoning": reasoning.strip(),
    }
    _think_log.append(entry)
    if len(_think_log) > _MAX_THINK_LOG:
        del _think_log[:-_MAX_THINK_LOG]
    return f"Thought logged ({len(reasoning)} chars)"


def get_think_log() -> list[dict]:
    """Internal — returns the full think log. Not exposed as an agent tool."""
    return list(_think_log)


def clear_think_log() -> None:
    """Internal — clears the think log on session restart."""
    _think_log.clear()


# ── Todo list ─────────────────────────────────────────────────────────────────
# Agent maintains a task list for multi-step work.
# Cleared each session restart.

_todos: list[dict] = []
_MAX_TODOS = 30


def todo_update(
    action: str,
    text: str = "",
    todo_id: str = "",
) -> str:
    """
    Manage your internal task list for multi-step canvas work.

    action options:
      "add"      — add a new task. Requires text.
                   Returns the new todo_id.
      "done"     — mark a task complete. Requires todo_id.
      "list"     — return all pending tasks.
                   Use this at the start of a multi-step sequence to
                   see what's left, or after resuming from a barge-in.

    Use this when:
    - You receive a complex instruction with multiple parts
    - You want to track what you've done and what remains
    - You resume after being interrupted (barge-in)
    - Before calling check_deferred_tasks() to see if background work landed

    Example workflow:
      todo_update("add", "Place water cycle diagram")
      todo_update("add", "Dispatch image generation for water cycle")
      todo_update("add", "Find YouTube video on water cycle")
      ... do the work ...
      todo_update("done", todo_id="abc123")
      todo_update("list")  # verify what's left

    Returns: status string describing the result.
    """
    if action == "add":
        if not text.strip():
            return "Error: text required for add"
        new_id = uuid.uuid4().hex[:8]
        _todos.append({
            "id": new_id,
            "text": text.strip(),
            "status": "pending",
            "added_at": time.time(),
            "done_at": None,
        })
        if len(_todos) > _MAX_TODOS:
            # Remove oldest completed tasks first
            completed = [t for t in _todos if t["status"] == "done"]
            if completed:
                _todos.remove(completed[0])
        pending_count = sum(1 for t in _todos if t["status"] == "pending")
        return f"Todo added id={new_id} | {pending_count} pending task(s)"

    elif action == "done":
        if not todo_id:
            return "Error: todo_id required for done"
        for t in _todos:
            if t["id"] == todo_id:
                t["status"] = "done"
                t["done_at"] = time.time()
                pending = [t2 for t2 in _todos if t2["status"] == "pending"]
                if pending:
                    next_task = pending[0]["text"][:60]
                    return f"Marked done. Next task: {next_task}"
                return "Marked done. All tasks complete."
        return f"Todo id={todo_id} not found"

    elif action == "list":
        pending = [t for t in _todos if t["status"] == "pending"]
        done = [t for t in _todos if t["status"] == "done"]
        if not pending and not done:
            return "Todo list is empty"
        lines = []
        if pending:
            lines.append(f"PENDING ({len(pending)}):")
            for t in pending:
                lines.append(f"  [{t['id']}] {t['text'][:80]}")
        if done:
            lines.append(f"DONE ({len(done)}):")
            for t in done[-3:]:  # show last 3 completed
                lines.append(f"  [✓] {t['text'][:60]}")
        return "\n".join(lines)

    else:
        return f"Unknown action '{action}'. Use: add | done | list"


def get_todos() -> list[dict]:
    """Internal — returns full todo list."""
    return list(_todos)


def clear_todos() -> None:
    """Internal — clears todos on session restart."""
    _todos.clear()


# ── Review scheduling ─────────────────────────────────────────────────────────

_review_queue: list[dict] = []


def schedule_review(
    intent: str,
    shape_ids: str = "",
) -> str:
    """
    Schedule a self-review of canvas work you just completed.
    The agent will zoom to the relevant shapes and verify the result.

    Use this AFTER completing a multi-shape placement to:
    - Check that arrows are correctly bound
    - Verify shapes don't overlap
    - Confirm text labels are correct
    - Catch placement errors before the user notices

    intent: describe what you're reviewing, e.g.
      "Check water cycle arrows are correctly connected"
      "Verify all 4 stages of digestion are placed and connected"

    shape_ids: comma-separated shape IDs to focus on (optional).
               If empty, uses the current viewport.

    Returns: confirmation string. The review runs in your next available cycle.
    """
    review_id = uuid.uuid4().hex[:8]
    ids = [s.strip() for s in shape_ids.split(",") if s.strip()] if shape_ids else []
    _review_queue.append({
        "id": review_id,
        "intent": intent.strip(),
        "shape_ids": ids,
        "scheduled_at": time.time(),
        "status": "pending",
    })
    return f"Review scheduled id={review_id}: '{intent[:60]}'"


def get_pending_reviews() -> list[dict]:
    """Internal — returns pending reviews for the agent loop to process."""
    return [r for r in _review_queue if r["status"] == "pending"]


def mark_review_done(review_id: str) -> None:
    """Internal — called after a review pass completes."""
    for r in _review_queue:
        if r["id"] == review_id:
            r["status"] = "done"
            break
