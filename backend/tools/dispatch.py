from agent_tasks import dispatch
from agent_tasks import dispatch, add_deferred_task, get_deferred_status_summary, format_task_board


def defer_task(instruction: str) -> str:
    """
    Hand off a canvas instruction to the background continuation agent.
    Use this when you are about to be interrupted or want a multi-step
    canvas task completed without blocking the live session.
    The task runs asynchronously — check back with check_deferred_tasks().
    """
    task_id = add_deferred_task(instruction)
    board = format_task_board()
    return f"Task deferred (id={task_id}): {instruction[:60]} | {board}"


def check_deferred_tasks() -> str:
    """
    Return a compact status summary of all tasks previously sent via defer_task.
    Call this after a pause to confirm deferred work is complete.
    """
    return get_deferred_status_summary()


def dispatch_research(query: str) -> str:
    dispatch("research", {"query": query}, source="live_agent")
    return f"Research dispatched: {query}"


def dispatch_image_gen(prompt: str) -> str:
    dispatch("image_gen", {"prompt": prompt}, source="live_agent")
    return f"Image generation dispatched: {prompt}"


def dispatch_youtube(query: str, count: int) -> str:
    payload = {"query": query}
    count = int(count)
    if count > 0:
        payload["count"] = count
        payload["max_results"] = count
    dispatch("youtube", payload, source="live_agent")
    if count > 0:
        return f"YouTube search dispatched: {query} ({count} video(s))"
    return f"YouTube search dispatched: {query}"


def dispatch_super_think() -> str:
    dispatch("super_think", {}, source="live_agent")
    return "SuperThink analysis started"


def dispatch_document(query: str, mode: str = "think") -> str:
        """
        Dispatch the DocumentAgent to process an uploaded document.

        In Think Mode (default):
            Places a full spatial map on canvas — title, summary, insights,
            and open questions as violet provocation notes.

        In Present Mode:
            Silent. Loads document text into memory only.
            Places one small green confirmation note.
            The agent can then answer audience questions grounded in the content.

        query: what to look for in the document, or just the filename
        mode: "think" | "explain" — defaults to current session mode
        """
        dispatch("document", {"query": query, "mode": mode}, source="live_agent")
        return f"Document analysis dispatched: {query} (mode={mode})"
