from agent_tasks import dispatch

def dispatch_research(query: str) -> str:
    dispatch("research", {"query": query}, source="live_agent")
    return f"Research dispatched: {query}"


def dispatch_image_gen(prompt: str) -> str:
    dispatch("image_gen", {"prompt": prompt}, source="live_agent")
    return f"Image generation dispatched: {prompt}"


def dispatch_youtube(query: str, count: int = 0) -> str:
    payload = {"query": query}
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


def dispatch_document(query: str) -> str:
    dispatch("document", {"query": query}, source="live_agent")
    return f"Document analysis dispatched: {query}"
