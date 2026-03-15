import asyncio

# ── Shared state ──────────────────────────────────────────────────────────────
canvas_action_queue: asyncio.Queue = asyncio.Queue()

canvas_state: dict = {
    "shapes": [],
    "shape_ids": [],
    "shape_count": 0,
    "_prev_ids": set(),
    "viewport": {"x": 0, "y": 0, "w": 1200, "h": 800, "zoom": 1.0},
    "selected_shape_ids": [],
    "current_page_id": None,
    "current_page_name": None,
    "pages": [],
}


def update_canvas_state(
    shapes: list,
    shape_count: int,
    viewport: dict = None,
    selected_shape_ids: list = None,
    current_page_id: str | None = None,
    current_page_name: str | None = None,
    pages: list | None = None,
) -> bool:
    """
    Called by main.py when a canvas_snapshot arrives.
    Returns True if the shape inventory actually changed.
    """
    new_ids = {s["id"] for s in shapes if isinstance(s, dict) and "id" in s}
    prev_ids = canvas_state["_prev_ids"]
    changed = new_ids != prev_ids

    canvas_state["shapes"] = shapes
    canvas_state["shape_ids"] = list(new_ids)
    canvas_state["shape_count"] = shape_count
    canvas_state["_prev_ids"] = new_ids

    if viewport:
        canvas_state["viewport"] = viewport
    if selected_shape_ids is not None:
        canvas_state["selected_shape_ids"] = selected_shape_ids
    if current_page_id is not None:
        canvas_state["current_page_id"] = current_page_id
    if current_page_name is not None:
        canvas_state["current_page_name"] = current_page_name
    if pages is not None:
        canvas_state["pages"] = pages

    # If canvas was cleared, reset the smart_write local placement registry
    if shape_count == 0 and len(prev_ids) > 0:
        try:
            from .smart_write import _clear_local_registry
            _clear_local_registry()
        except ImportError:
            pass

    return changed
