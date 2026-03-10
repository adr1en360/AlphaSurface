"""
AlphaSurface — Canvas tools for ADK LlmAgent.

ADK rules for Google AI auto-schema generation:
  - NO default parameter values
  - NO union types (str | None) — use Optional fields via docstring only
  - All parameters must be simple types: str, float, int, bool, list[str]
  - Literal types ARE supported
"""

import asyncio
from typing import Literal

# ── Shared action queue ────────────────────────────────────────────────────────
canvas_action_queue: asyncio.Queue = asyncio.Queue()

# ── Canvas state mirror (written by main.py) ──────────────────────────────────
canvas_state: dict = {
    "shape_ids": [],
    "shape_count": 0,
}

def update_canvas_state(shape_ids: list[str], shape_count: int) -> None:
    """Called by main.py whenever the browser sends a canvas_snapshot."""
    canvas_state["shape_ids"] = shape_ids
    canvas_state["shape_count"] = shape_count


async def _emit(action_type: str, payload: dict) -> dict:
    await canvas_action_queue.put({"type": action_type, "payload": payload})
    return {"status": "ok", "action": action_type}


# ── Tools ─────────────────────────────────────────────────────────────────────

async def add_text_to_canvas(
    text: str,
    x: float,
    y: float,
    size: Literal["s", "m", "l", "xl"],
    color: Literal["black", "grey", "light-violet", "violet", "blue", "light-blue", "yellow", "orange", "green", "light-green", "light-red", "red", "white"],
) -> dict:
    """Add a plain text label to the canvas. Use for titles or short annotations."""
    return await _emit("add_text", {
        "text": text, "x": x, "y": y, "size": size, "color": color,
    })


async def add_note_to_canvas(
    text: str,
    x: float,
    y: float,
    size: Literal["s", "m", "l", "xl"],
    color: Literal["black", "grey", "light-violet", "violet", "blue", "light-blue", "yellow", "orange", "green", "light-green", "light-red", "red", "white"],
) -> dict:
    """
    Add a sticky note to the canvas.
    Use for ideas, Sarkar provocations, questions, or reflections.
    Think Mode: use color=violet. Explain Mode: use color=blue or yellow.
    """
    return await _emit("add_note", {
        "text": text, "x": x, "y": y, "size": size, "color": color,
    })


async def add_geo_to_canvas(
    geo: Literal["rectangle", "ellipse", "triangle", "diamond", "hexagon", "star"],
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    color: Literal["black", "grey", "light-violet", "violet", "blue", "light-blue", "yellow", "orange", "green", "light-green", "light-red", "red", "white"],
    fill: Literal["none", "semi", "solid"],
    size: Literal["s", "m", "l", "xl"],
) -> dict:
    """Add a geometric shape to the canvas. Use for concept boxes, diagrams, flowcharts."""
    return await _emit("add_geo", {
        "geo": geo, "text": text, "x": x, "y": y,
        "w": w, "h": h, "color": color, "fill": fill, "size": size,
    })


async def bind_arrow(
    from_shape_id: str,
    to_shape_id: str,
    label: str,
    color: Literal["black", "grey", "light-violet", "violet", "blue", "light-blue", "yellow", "orange", "green", "light-green", "light-red", "red", "white"],
) -> dict:
    """
    Draw a directional arrow between two existing shapes.
    Call list_canvas_shapes first to get real shape IDs.
    Use to show relationships, causality, or sequence.
    """
    known = canvas_state["shape_ids"]
    if from_shape_id not in known or to_shape_id not in known:
        return {
            "status": "error",
            "reason": f"Unknown shape IDs. Known IDs on canvas: {known}",
        }
    return await _emit("bind_arrow", {
        "fromShapeId": from_shape_id,
        "toShapeId": to_shape_id,
        "label": label,
        "color": color,
    })


async def list_canvas_shapes() -> dict:
    """
    Return the current list of shape IDs on the canvas.
    Always call this before bind_arrow, delete_shapes, focus_shape, or move_shape.
    """
    return {
        "shape_ids": canvas_state["shape_ids"],
        "shape_count": canvas_state["shape_count"],
    }


async def delete_shapes(shape_ids: list[str]) -> dict:
    """Delete one or more shapes by their IDs. Call list_canvas_shapes first."""
    return await _emit("delete_shapes", {"shapeIds": shape_ids})


async def move_shape(shape_id: str, x: float, y: float) -> dict:
    """Move an existing shape to a new canvas position."""
    return await _emit("move_shape", {"shapeId": shape_id, "x": x, "y": y})


async def update_shape_text(shape_id: str, text: str) -> dict:
    """Update the text content of an existing shape."""
    return await _emit("update_shape", {"shapeId": shape_id, "text": text})


async def update_shape_color(shape_id: str, color: Literal["black", "grey", "light-violet", "violet", "blue", "light-blue", "yellow", "orange", "green", "light-green", "light-red", "red", "white"]) -> dict:
    """Update the color of an existing shape."""
    return await _emit("update_shape", {"shapeId": shape_id, "color": color})


async def select_shapes(shape_ids: list[str]) -> dict:
    """Highlight specific shapes to draw the user's attention to them."""
    return await _emit("select_shapes", {"shapeIds": shape_ids})


async def zoom_to_fit() -> dict:
    """Zoom the canvas camera to show all content. Call after adding many shapes."""
    return await _emit("zoom_to_fit", {})


async def focus_shape(shape_id: str) -> dict:
    """Pan and zoom the camera to center on a specific shape."""
    return await _emit("focus_shape", {"shapeId": shape_id})


async def clear_canvas() -> dict:
    """Remove all shapes from the canvas. Only use when user explicitly asks."""
    return await _emit("clear_canvas", {})


async def add_embed_to_canvas(
    url: str,
    x: float,
    y: float,
    w: float,
    h: float,
) -> dict:
    """
    Embed a live interactive iframe on the canvas.
    Supported URLs: YouTube videos, Figma files, Google Maps, CodeSandbox.
    Default size: w=560, h=315. Use larger sizes for Figma (w=800, h=600).
    """
    return await _emit("add_embed", {"url": url, "x": x, "y": y, "w": w, "h": h})


async def add_bookmark_to_canvas(
    url: str,
    x: float,
    y: float,
) -> dict:
    """
    Add a rich bookmark card (title, description, thumbnail) for any URL.
    Use for referencing web resources, articles, or documentation on the canvas.
    """
    return await _emit("add_bookmark", {"url": url, "x": x, "y": y})


# ── Tool registry ─────────────────────────────────────────────────────────────
ALL_TOOLS = [
    add_text_to_canvas,
    add_note_to_canvas,
    add_geo_to_canvas,
    bind_arrow,
    list_canvas_shapes,
    delete_shapes,
    move_shape,
    update_shape_text,
    update_shape_color,
    select_shapes,
    zoom_to_fit,
    focus_shape,
    clear_canvas,
    add_embed_to_canvas,
    add_bookmark_to_canvas,
]
