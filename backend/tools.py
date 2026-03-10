"""
AlphaSurface — Canvas tool definitions for the ADK agent.

ONLY tools implemented in App.jsx are listed here.
The agent cannot use tools not in ALL_TOOLS.

Available:  add_text, add_note, add_geo, add_arrow, bind_arrow,
            move_shape, update_shape, delete_shapes, zoom_to_fit,
            focus_shape, select_shapes, clear_canvas,
            add_embed, add_bookmark, list_canvas_shapes

NOT available (removed): add_image, add_draw, add_frame,
            group_shapes, ungroup_shapes, resize_shape,
            reorder_shape, set_camera, process_information
"""

import asyncio

# ── Shared state ──────────────────────────────────────────────────────────────
canvas_action_queue: asyncio.Queue = asyncio.Queue()

# Rich state: each shape has id, type, x, y, w, h so agent avoids overlaps
canvas_state: dict = {
    "shapes": [],      # list of {id, type, x, y, w, h}
    "shape_ids": [],   # flat list for quick lookup
    "shape_count": 0,
}


def update_canvas_state(shapes: list, shape_count: int):
    """Called by main.py when a canvas_snapshot arrives from the browser."""
    canvas_state["shapes"] = shapes
    canvas_state["shape_ids"] = [s["id"] for s in shapes if isinstance(s, dict)]
    canvas_state["shape_count"] = shape_count


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
        "payload": {"text": text, "geo": geo or "rectangle", "x": x, "y": y, "w": w or 200, "h": h or 120, "color": color or "blue", "fill": fill or "semi"}
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
        "payload": {"fromShapeId": from_shape_id, "toShapeId": to_shape_id, "label": label or "", "color": color or "black"}
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

def move_shape(
    shape_id: str,
    x: int,
    y: int,
) -> str:
    """Move a shape to a new canvas position. Call list_canvas_shapes first.

    Args:
        shape_id: Shape ID from list_canvas_shapes.
        x: New X position.
        y: New Y position.
    """
    canvas_action_queue.put_nowait({"type": "move_shape", "payload": {"shapeId": shape_id, "x": x, "y": y}})
    return f"Moved {shape_id} to ({x},{y})"


def update_shape(
    shape_id: str,
    text: str,
    color: str,
) -> str:
    """Update a shape's text or color. Call list_canvas_shapes first.

    Args:
        shape_id: Shape ID from list_canvas_shapes.
        text: New text content. Pass empty string to keep current text.
        color: New color. Pass empty string to keep current color.
    """
    payload: dict = {"shapeId": shape_id}
    if text: payload["text"] = text
    if color: payload["color"] = color
    canvas_action_queue.put_nowait({"type": "update_shape", "payload": payload})
    return f"Updated {shape_id}"


def delete_shapes(
    shape_ids: list[str],
) -> str:
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


# ── Tool registry ─────────────────────────────────────────────────────────────
ALL_TOOLS = [
    list_canvas_shapes,
    add_text_to_canvas,
    add_note_to_canvas,
    add_geo_to_canvas,
    add_arrow_to_canvas,
    bind_arrow,
    add_embed_to_canvas,
    add_bookmark_to_canvas,
    move_shape,
    update_shape,
    delete_shapes,
    zoom_to_fit,
    focus_shape,
    select_shapes,
    clear_canvas,
]
