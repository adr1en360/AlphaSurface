from agent_tasks import dispatch

def dispatch_research(query: str) -> str:
    dispatch("research", {"query": query}, source="live_agent")
    return f"Research dispatched: {query}"


def dispatch_image_gen(prompt: str) -> str:
    dispatch("image_gen", {"prompt": prompt}, source="live_agent")
    return f"Image generation dispatched: {prompt}"


def dispatch_youtube(query: str) -> str:
    dispatch("youtube", {"query": query}, source="live_agent")
    return f"YouTube search dispatched: {query}"


def dispatch_super_think() -> str:
    dispatch("super_think", {}, source="live_agent")
    return "SuperThink analysis started"


def dispatch_document(query: str) -> str:
    dispatch("document", {"query": query}, source="live_agent")
    return f"Document analysis dispatched: {query}"
