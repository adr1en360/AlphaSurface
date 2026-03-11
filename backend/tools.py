"""
AlphaSurface — Canvas tool definitions for the ADK agent.

ONLY tools implemented in App.jsx are listed here.
The agent cannot use tools not in ALL_TOOLS.

Available:  add_text, add_note, add_geo, add_arrow, bind_arrow,
            move_shape, update_shape, delete_shapes, zoom_to_fit,
            focus_shape, select_shapes, clear_canvas,
            add_embed, add_bookmark, list_canvas_shapes,
            memory_read, memory_write, scan_canvas_text   ← NEW

NOT available (removed): add_image, add_draw, add_frame,
            group_shapes, ungroup_shapes, resize_shape,
            reorder_shape, set_camera, process_information
"""

import asyncio

from memory import memory_store
from agent_tasks import dispatch

# ── Shared state ──────────────────────────────────────────────────────────────
canvas_action_queue: asyncio.Queue = asyncio.Queue()

# Rich state: each shape has id, type, x, y, w, h, text
canvas_state: dict = {
    "shapes": [],
    "shape_ids": [],
    "shape_count": 0,
    "_prev_ids": set(),   # used to detect changes for event bus
}


def update_canvas_state(shapes: list, shape_count: int) -> bool:
    """
    Called by main.py when a canvas_snapshot arrives.
    Returns True if the shape inventory actually changed (new or deleted shapes).
    """
    new_ids = {s["id"] for s in shapes if isinstance(s, dict) and "id" in s}
    changed = new_ids != canvas_state["_prev_ids"]
    canvas_state["shapes"] = shapes
    canvas_state["shape_ids"] = list(new_ids)
    canvas_state["shape_count"] = shape_count
    canvas_state["_prev_ids"] = new_ids
    return changed


# ── READ ──────────────────────────────────────────────────────────────────────

def list_canvas_shapes() -> dict:
    """
    Returns all shapes on the canvas with positions (x, y, w, h) and type.
    ALWAYS call this before bind_arrow, move_shape, delete_shapes, focus_shape,
    update_shape — you need real IDs and positions.
    """
    return {
        "shape_count": canvas_state["shape_count"],
        "shapes": canvas_state["shapes"],
    }


def find_empty_space_on_canvas(width: int, height: int) -> dict:
    """
    Finds a large enough empty coordinate space on the canvas to place new shapes 
    without overlapping existing ones. 
    Returns {"x": suggest_x, "y": suggest_y}.
    
    Args:
        width: the required width of the empty space. Use 400 if unsure.
        height: the required height of the empty space. Use 400 if unsure.
    """
    shapes = canvas_state["shapes"]
    
    # Simple grid search for empty space
    # Canvas space: x range 80–1500, y range 60–950
    for y in range(80, 950 - height, 100):
        for x in range(80, 1500 - width, 100):
            overlap = False
            for shape in shapes:
                if not isinstance(shape, dict): continue
                sx = shape.get("x", 0)
                sy = shape.get("y", 0)
                sw = shape.get("w", 200)
                sh = shape.get("h", 120)
                # Check for rectangle intersection
                if (x < sx + sw + 150 and x + width + 150 > sx and
                    y < sy + sh + 150 and y + height + 150 > sy):
                    overlap = True
                    break
            if not overlap:
                return {"x": x, "y": y, "status": "found"}
                
    # Fallback if canvas is too full
    return {"x": 800, "y": 500, "status": "canvas full, returning default"}


def get_shapes_near_coordinate(x: int, y: int, radius: int) -> dict:
    """
    Finds all shapes within a specific radius of a coordinate point.
    Useful for reading context around a specific area or finding what the user is working on in a specific region.
    
    Args:
        x: Center X coordinate.
        y: Center Y coordinate.
        radius: Search radius. Use 300 if unsure.
    """
    shapes = canvas_state["shapes"]
    nearby = []
    
    for shape in shapes:
        if not isinstance(shape, dict): continue
        sx = shape.get("x", 0)
        sy = shape.get("y", 0)
        sw = shape.get("w", 200)
        sh = shape.get("h", 120)
        
        # Center of the shape
        cx = sx + (sw / 2)
        cy = sy + (sh / 2)
        
        # Distance squared
        dist_sq = (cx - x)**2 + (cy - y)**2
        if dist_sq <= radius**2:
            nearby.append({
                "id": shape.get("id"),
                "text": shape.get("text") or shape.get("label") or "",
                "type": shape.get("type"),
                "distance": int(dist_sq**0.5)
            })
            
    # Sort by closest first
    nearby.sort(key=lambda s: s["distance"])
    return {"nearby_shapes": nearby, "count": len(nearby)}



def scan_canvas_text() -> dict:
    """
    Returns all text content from canvas shapes, grouped by type.
    Use this to understand WHAT the user has written without calling list_canvas_shapes.
    Useful for: persona analysis, provocation targeting, context summarisation.
    """
    notes = []
    geo_labels = []
    text_labels = []
    other = []

    for shape in canvas_state["shapes"]:
        if not isinstance(shape, dict):
            continue
        text = shape.get("text") or shape.get("label") or ""
        if not text.strip():
            continue
        shape_type = shape.get("type", "")
        entry = {"id": shape.get("id", ""), "text": text.strip(), "x": shape.get("x", 0), "y": shape.get("y", 0)}
        if shape_type == "note":
            notes.append(entry)
        elif shape_type == "geo":
            geo_labels.append(entry)
        elif shape_type == "text":
            text_labels.append(entry)
        else:
            other.append(entry)

    return {
        "sticky_notes": notes,
        "geo_shapes": geo_labels,
        "text_labels": text_labels,
        "other": other,
        "total_text_shapes": len(notes) + len(geo_labels) + len(text_labels) + len(other),
    }


# ── MEMORY ────────────────────────────────────────────────────────────────────

def memory_read(user_id: str) -> dict:
    """
    Read the persisted user profile from memory.
    Returns a dict with keys like: communication_style, domain_interests,
    response_preferences, observed_traits, session_count.
    Returns {} for a new user.

    Args:
        user_id: The user's unique identifier. Use "user" if unsure.
    """
    store = memory_store()
    if hasattr(store, "read_sync"):
        return store.read_sync(user_id)
    return {}


def memory_write(user_id: str, key: str, value: str) -> str:
    """
    Write a single observation about the user to persistent memory.
    Use this to record things you notice about how the user thinks and communicates.

    Examples:
        memory_write("user", "communication_style", "prefers concise single-sentence answers")
        memory_write("user", "domain", "product management, SaaS")
        memory_write("user", "response_preference", "diagrams over text")
        memory_write("user", "provocation_preference", "specific questions not abstract ones")

    Args:
        user_id: The user's unique identifier. Use "user" if unsure.
        key: Profile field name (snake_case).
        value: The observed value as a string.
    """
    store = memory_store()
    if hasattr(store, "merge_sync"):
        store.merge_sync(user_id, {key: value})
    return f"Memory updated: {key} = {value}"


# ── WRITE ─────────────────────────────────────────────────────────────────────

def add_text_to_canvas(
    text: str,
    x: int,
    y: int,
    color: str,
    size: str,
) -> str:
    """Place a plain text label on the canvas.

    Args:
        text: The text label to display.
        x: Canvas X position (100-1400). Use 300 if unsure.
        y: Canvas Y position (80-900). Use 300 if unsure.
        color: One of: black, red, blue, green, orange, violet, yellow, grey, light-blue, light-green, light-red, light-violet.
        size: One of: s, m, l, xl.
    """
    canvas_action_queue.put_nowait({
        "type": "add_text",
        "payload": {"text": text, "x": x, "y": y, "color": color or "black", "size": size or "m"}
    })
    return f"Text placed at ({x},{y})"


def add_note_to_canvas(
    text: str,
    x: int,
    y: int,
    color: str,
    size: str,
) -> str:
    """
    Place a sticky note on the canvas.
    Color convention:
      violet = Sarkar provocation (question/challenge)
      yellow = neutral idea
      green  = supporting evidence
      red    = counterargument
      blue   = fact / definition
    Use x=400, y=300, size=m if unsure.
    """
    canvas_action_queue.put_nowait({
        "type": "add_note",
        "payload": {"text": text, "x": x, "y": y, "color": color or "yellow", "size": size or "m"}
    })
    return f"Note placed at ({x},{y})"


def add_geo_to_canvas(
    text: str,
    geo: str,
    x: int,
    y: int,
    w: int,
    h: int,
    color: str,
    fill: str,
) -> str:
    """Place a geometric shape (rectangle, ellipse, diamond, etc.) on the canvas.

    Args:
        text: Label inside the shape.
        geo: rectangle|ellipse|triangle|diamond|hexagon|star|oval|rhombus|pentagon|cloud. Use rectangle if unsure.
        x: Canvas X position. Use 300 if unsure.
        y: Canvas Y position. Use 300 if unsure.
        w: Width in pixels (100-500). Use 200 if unsure.
        h: Height in pixels (60-300). Use 120 if unsure.
        color: blue|red|green|orange|violet|yellow|grey|light-blue|black. Use blue if unsure.
        fill: none|semi|solid|pattern. Use semi if unsure.
    """
    canvas_action_queue.put_nowait({
        "type": "add_geo",
        "payload": {
            "text": text, "geo": geo or "rectangle",
            "x": x, "y": y, "w": w or 200, "h": h or 120,
            "color": color or "blue", "fill": fill or "semi"
        }
    })
    return f"{geo} at ({x},{y})"


def add_arrow_to_canvas(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    label: str,
    color: str,
) -> str:
    """Draw a free arrow between two canvas coordinates.

    Args:
        x1: Start X coordinate.
        y1: Start Y coordinate.
        x2: End X coordinate.
        y2: End Y coordinate.
        label: Arrow label text. Pass empty string for no label.
        color: black|red|blue|green|grey. Use black if unsure.
    """
    canvas_action_queue.put_nowait({
        "type": "add_arrow",
        "payload": {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label": label or "", "color": color or "black"}
    })
    return f"Arrow ({x1},{y1})→({x2},{y2})"


def bind_arrow(
    from_shape_id: str,
    to_shape_id: str,
    label: str,
    color: str,
) -> str:
    """
    Create an arrow snapped to two existing shapes by ID.
    The arrow stays connected even when shapes are moved.
    MUST call list_canvas_shapes first.

    Args:
        from_shape_id: Source shape ID (from list_canvas_shapes).
        to_shape_id: Target shape ID (from list_canvas_shapes).
        label: Arrow label text. Pass empty string for no label.
        color: black|red|blue|green|grey. Use black if unsure.
    """
    canvas_action_queue.put_nowait({
        "type": "bind_arrow",
        "payload": {
            "fromShapeId": from_shape_id, "toShapeId": to_shape_id,
            "label": label or "", "color": color or "black"
        }
    })
    return f"Bound arrow {from_shape_id}→{to_shape_id}"


def add_embed_to_canvas(
    url: str,
    x: int,
    y: int,
    w: int,
    h: int,
) -> str:
    """Embed a live interactive iframe (YouTube video, Figma, map, etc.) on the canvas.

    Args:
        url: YouTube, Figma, CodeSandbox, Replit, Google Maps, GitHub Gist, Spotify, Observable, or Excalidraw URL.
        x: Canvas X position. Use 300 if unsure.
        y: Canvas Y position. Use 300 if unsure.
        w: Width in pixels. Use 560 if unsure.
        h: Height in pixels. Use 315 if unsure.
    """
    canvas_action_queue.put_nowait({
        "type": "add_embed",
        "payload": {"url": url, "x": x, "y": y, "w": w or 560, "h": h or 315}
    })
    return f"Embedded {url}"


def add_bookmark_to_canvas(
    url: str,
    x: int,
    y: int,
) -> str:
    """Add a rich link card (title, thumbnail) for any URL — articles, docs, repos.

    Args:
        url: Any web URL.
        x: Canvas X position. Use 300 if unsure.
        y: Canvas Y position. Use 300 if unsure.
    """
    canvas_action_queue.put_nowait({
        "type": "add_bookmark",
        "payload": {"url": url, "x": x, "y": y}
    })
    return f"Bookmarked {url}"


# ── EDIT ──────────────────────────────────────────────────────────────────────

def move_shape(shape_id: str, x: int, y: int) -> str:
    """Move a shape to a new canvas position. Call list_canvas_shapes first.

    Args:
        shape_id: Shape ID from list_canvas_shapes.
        x: New X position.
        y: New Y position.
    """
    canvas_action_queue.put_nowait({"type": "move_shape", "payload": {"shapeId": shape_id, "x": x, "y": y}})
    return f"Moved {shape_id} to ({x},{y})"


def update_shape(shape_id: str, text: str, color: str) -> str:
    """Update a shape's text or color. Call list_canvas_shapes first.

    Args:
        shape_id: Shape ID from list_canvas_shapes.
        text: New text content. Pass empty string to keep current text.
        color: New color. Pass empty string to keep current color.
    """
    payload: dict = {"shapeId": shape_id}
    if text:
        payload["text"] = text
    if color:
        payload["color"] = color
    canvas_action_queue.put_nowait({"type": "update_shape", "payload": payload})
    return f"Updated {shape_id}"


def delete_shapes(shape_ids: list[str]) -> str:
    """Delete shapes by ID. Call list_canvas_shapes first.

    Args:
        shape_ids: List of shape IDs to delete.
    """
    canvas_action_queue.put_nowait({"type": "delete_shapes", "payload": {"shapeIds": shape_ids}})
    return f"Deleted {len(shape_ids)} shape(s)"


# ── NAVIGATE ──────────────────────────────────────────────────────────────────

def zoom_to_fit() -> str:
    """Zoom out to show all shapes. Call after adding 3+ shapes."""
    canvas_action_queue.put_nowait({"type": "zoom_to_fit", "payload": {}})
    return "Zoomed to fit"


def focus_shape(shape_id: str) -> str:
    """Zoom and select a specific shape. Call list_canvas_shapes first.

    Args:
        shape_id: Shape ID to zoom into.
    """
    canvas_action_queue.put_nowait({"type": "focus_shape", "payload": {"shapeId": shape_id}})
    return f"Focused on {shape_id}"


def select_shapes(shape_ids: list[str]) -> str:
    """Highlight specific shapes on the canvas.

    Args:
        shape_ids: Shape IDs to select.
    """
    canvas_action_queue.put_nowait({"type": "select_shapes", "payload": {"shapeIds": shape_ids}})
    return f"Selected {len(shape_ids)} shape(s)"


def clear_canvas() -> str:
    """Delete ALL shapes. Use only when explicitly asked."""
    canvas_action_queue.put_nowait({"type": "clear_canvas", "payload": {}})
    return "Canvas cleared"


def dispatch_research(query: str) -> str:
    """Send a web search query to ResearchAgent. It will search the web and place results on canvas. Use for any factual or current-events question."""
    dispatch("research", {"query": query}, source="live_agent")
    return f"Research dispatched: {query}"


def dispatch_image_gen(prompt: str) -> str:
    """Send an image generation prompt to ImageGenAgent. It will generate an image and place it on canvas."""
    dispatch("image_gen", {"prompt": prompt}, source="live_agent")
    return f"Image generation dispatched: {prompt}"


def dispatch_youtube(query: str) -> str:
    """Find YouTube videos on a topic and embed them on the canvas. Use when the user asks to find or show a video about something."""
    dispatch("youtube", {"query": query}, source="live_agent")
    return f"YouTube search dispatched: {query}"


def dispatch_super_think() -> str:
    """
    Trigger SuperThink — a deep multi-step analysis of everything currently on the canvas.
    Places three clusters: Synthesis (what it all means), Tensions (contradictions),
    and Open Questions (what's missing). Use when the user asks to 'think harder',
    'deep dive', 'analyze this', or 'super think'.
    """
    dispatch("super_think", {}, source="live_agent")
    return "SuperThink analysis started"


def dispatch_document(query: str) -> str:
    """
    Analyze a document (PDF or Word) in the documents folder.
    Use when the user mentions a document name or says 'analyze this document'.
    Provide a specific document name if mentioned, or a query about what to find.
    """
    dispatch("document", {"query": query}, source="live_agent")
    return f"Document analysis dispatched: {query}"


# ── Tool registry ─────────────────────────────────────────────────────────────
ALL_TOOLS = [
    # READ
    list_canvas_shapes,
    scan_canvas_text,
    find_empty_space_on_canvas,
    get_shapes_near_coordinate,
    # MEMORY
    memory_read,
    memory_write,
    # WRITE
    add_text_to_canvas,
    add_note_to_canvas,
    add_geo_to_canvas,
    add_arrow_to_canvas,
    bind_arrow,
    add_embed_to_canvas,
    add_bookmark_to_canvas,
    # EDIT
    move_shape,
    update_shape,
    delete_shapes,
    # NAVIGATE
    zoom_to_fit,
    focus_shape,
    select_shapes,
    clear_canvas,
    # DISPATCH (sub-agents)
    dispatch_research,
    dispatch_image_gen,
    dispatch_youtube,
    dispatch_super_think,
    dispatch_document,
]
