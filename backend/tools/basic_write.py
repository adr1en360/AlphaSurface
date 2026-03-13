from .state import canvas_state, canvas_action_queue
from memory import memory_store
import uuid

_VALID_GEO = {
    "cloud", "rectangle", "ellipse", "triangle", "diamond", "pentagon",
    "hexagon", "octagon", "star", "rhombus", "rhombus-2", "oval",
    "trapezoid", "arrow-right", "arrow-left", "arrow-up", "arrow-down",
    "x-box", "check-box", "heart",
}

_GEO_ALIASES = {
    "rounded_rectangle": "rectangle",
    "rounded-rectangle": "rectangle",
    "rounded rect": "rectangle",
    "roundedrect": "rectangle",
    "roundedrectangle": "rectangle",
    "rect": "rectangle",
    "box": "rectangle",
    "circle": "ellipse",
}

_VALID_FILL = {"none", "semi", "solid", "pattern", "fill", "lined-fill"}

_VALID_COLORS = {
    "black", "grey", "light-violet", "violet", "blue", "light-blue",
    "yellow", "orange", "green", "light-green", "light-red", "red", "white",
}

_COLOR_ALIASES = {
    "gray": "grey",
    "purple": "violet",
    "light_purple": "light-violet",
    "light-purple": "light-violet",
    "light violet": "light-violet",
    "light_blue": "light-blue",
    "light blue": "light-blue",
    "light_green": "light-green",
    "light green": "light-green",
    "light_red": "light-red",
    "light red": "light-red",
}

_FILL_ALIASES = {
    "filled": "solid",
    "outline": "none",
    "transparent": "none",
    "half": "semi",
}


def _normalize_geo(geo: str) -> str:
    g = (geo or "rectangle").strip().lower().replace("_", "-")
    g = _GEO_ALIASES.get(g, _GEO_ALIASES.get(g.replace("-", ""), g))
    return g if g in _VALID_GEO else "rectangle"


def _normalize_fill(fill: str) -> str:
    f = (fill or "semi").strip().lower().replace("_", "-")
    f = _FILL_ALIASES.get(f, f)
    return f if f in _VALID_FILL else "semi"


def _normalize_color(color: str, default: str) -> str:
    c = (color or default).strip().lower().replace("_", "-")
    c = _COLOR_ALIASES.get(c, c)
    return c if c in _VALID_COLORS else default


def _find_non_overlapping_xy(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    shapes = canvas_state.get("shapes", [])

    def overlaps(px: int, py: int) -> bool:
        pad = 28
        for s in shapes:
            if not isinstance(s, dict):
                continue
            sx = int(s.get("x", 0))
            sy = int(s.get("y", 0))
            sw = int(s.get("w", 220))
            sh = int(s.get("h", 120))
            if (
                px < sx + sw + pad
                and px + w > sx - pad
                and py < sy + sh + pad
                and py + h > sy - pad
            ):
                return True
        return False

    if not overlaps(x, y):
        return x, y

    for ring in range(1, 12):
        for dx, dy in [
            (ring * 260, 0),
            (0, ring * 160),
            (-ring * 260, 0),
            (0, -ring * 160),
            (ring * 260, ring * 160),
            (-ring * 260, ring * 160),
            (ring * 260, -ring * 160),
            (-ring * 260, -ring * 160),
        ]:
            tx, ty = x + dx, y + dy
            if not overlaps(tx, ty):
                return tx, ty

    return x + 320, y + 220


def _new_shape_id(prefix: str) -> str:
    return f"shape:{prefix}_{uuid.uuid4().hex[:10]}"


def _normalize_linked_to(linked_to) -> list[str]:
    if linked_to is None:
        return []
    if isinstance(linked_to, list):
        return [str(item).strip() for item in linked_to if str(item).strip()]
    if isinstance(linked_to, str):
        return [item.strip() for item in linked_to.split(",") if item.strip()]
    return [str(linked_to).strip()] if str(linked_to).strip() else []


def _semantic_meta(
    semantic_role: str,
    source: str = "live_agent",
    confidence: float = 0.75,
    linked_to = "",
) -> dict:
    return {
        "semanticRole": semantic_role,
        "source": source,
        "confidence": float(confidence),
        "linked_to": _normalize_linked_to(linked_to),
        "addedBy": source,
    }

def list_canvas_shapes() -> dict:
    return {
        "shape_count": canvas_state["shape_count"],
        "shapes": canvas_state["shapes"],
    }


def scan_canvas_text() -> dict:
    notes, geo_labels, text_labels, other = [], [], [], []

    for shape in canvas_state["shapes"]:
        if not isinstance(shape, dict):
            continue
        text = shape.get("text") or ""
        if not text.strip():
            continue
        shape_type = shape.get("type", "")
        entry = {
            "id": shape.get("id", ""),
            "text": text.strip(),
            "x": shape.get("x", 0), "y": shape.get("y", 0),
            "color": shape.get("color", ""),
            "semanticRole": shape.get("meta", {}).get("semanticRole", "unknown"),
        }
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


def memory_read(user_id: str) -> dict:
    store = memory_store()
    if hasattr(store, "read_sync"):
        return store.read_sync(user_id)
    return {}


def memory_write(user_id: str, key: str, value: str) -> str:
    store = memory_store()
    if hasattr(store, "merge_sync"):
        store.merge_sync(user_id, {key: value})
    return f"Memory updated: {key} = {value}"


def add_text_to_canvas(
    text: str,
    x: int,
    y: int,
    color: str,
    size: str,
    semantic_role: str = "text",
    source: str = "live_agent",
    confidence: float = 0.8,
    linked_to: str = "",
) -> str:
    if size not in ["s", "m", "l", "xl"]:
        size = "m"
    normalized_color = _normalize_color(color, "black")
    x, y = _find_non_overlapping_xy(int(x), int(y), 260, 88)
    shape_id = _new_shape_id("text")
    canvas_action_queue.put_nowait({
        "type": "add_text",
        "payload": {
            "id": shape_id,
            "text": text,
            "x": x,
            "y": y,
            "color": normalized_color,
            "size": size,
            "meta": _semantic_meta(semantic_role, source, confidence, linked_to),
        }
    })
    return f"Text placed at ({x},{y})"


def add_note_to_canvas(
    text: str,
    x: int,
    y: int,
    color: str,
    size: str,
    semantic_role: str = "note",
    source: str = "live_agent",
    confidence: float = 0.75,
    linked_to: str = "",
) -> str:
    if size not in ["s", "m", "l", "xl"]:
        size = "m"
    normalized_color = _normalize_color(color, "yellow")
    x, y = _find_non_overlapping_xy(int(x), int(y), 280, 180)
    shape_id = _new_shape_id("note")
    if normalized_color in {"light-violet", "violet"} and "?" in (text or ""):
        semantic_role = "provocation"
    canvas_action_queue.put_nowait({
        "type": "add_note",
        "payload": {
            "id": shape_id,
            "text": text,
            "x": x,
            "y": y,
            "color": normalized_color,
            "size": size,
            "meta": _semantic_meta(semantic_role, source, confidence, linked_to),
        }
    })
    return f"Note placed at ({x},{y})"


def add_geo_to_canvas(text: str, geo: str, x: int, y: int,
                      w: int, h: int, color: str, fill: str,
                      semantic_role: str = "geo",
                      source: str = "live_agent",
                      confidence: float = 0.8,
                      linked_to: str = "") -> str:
    normalized_geo = _normalize_geo(geo)
    normalized_fill = _normalize_fill(fill)
    normalized_color = _normalize_color(color, "blue")
    final_w = int(w or 200)
    final_h = int(h or 120)
    x, y = _find_non_overlapping_xy(int(x), int(y), final_w, final_h)
    shape_id = _new_shape_id("geo")
    canvas_action_queue.put_nowait({
        "type": "add_geo",
        "payload": {
            "id": shape_id,
            "text": text, "geo": normalized_geo,
            "x": x, "y": y, "w": final_w, "h": final_h,
            "color": normalized_color, "fill": normalized_fill,
            "meta": _semantic_meta(semantic_role, source, confidence, linked_to),
        }
    })
    return f"{normalized_geo} at ({x},{y})"


def add_arrow_to_canvas(x1: int, y1: int, x2: int, y2: int,
                        label: str, color: str) -> str:
    normalized_color = _normalize_color(color, "black")
    canvas_action_queue.put_nowait({
        "type": "add_arrow",
        "payload": {"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "label": label or "", "color": normalized_color}
    })
    return f"Arrow ({x1},{y1})→({x2},{y2})"


def bind_arrow(from_shape_id: str, to_shape_id: str,
               label: str, color: str) -> str:
    normalized_color = _normalize_color(color, "black")
    canvas_action_queue.put_nowait({
        "type": "bind_arrow",
        "payload": {"fromShapeId": from_shape_id, "toShapeId": to_shape_id,
                    "label": label or "", "color": normalized_color}
    })
    return f"Bound arrow {from_shape_id}→{to_shape_id}"


def add_embed_to_canvas(url: str, x: int, y: int, w: int, h: int) -> str:
    final_w = int(w or 560)
    final_h = int(h or 315)
    x, y = _find_non_overlapping_xy(int(x), int(y), final_w, final_h)
    canvas_action_queue.put_nowait({
        "type": "add_embed",
        "payload": {"url": url, "x": x, "y": y, "w": final_w, "h": final_h}
    })
    return f"Embedded {url}"


def add_bookmark_to_canvas(
    url: str,
    x: int,
    y: int,
    semantic_role: str = "bookmark",
    source: str = "live_agent",
    confidence: float = 0.7,
    linked_to: str = "",
) -> str:
    x, y = _find_non_overlapping_xy(int(x), int(y), 320, 180)
    shape_id = _new_shape_id("bookmark")
    canvas_action_queue.put_nowait({
        "type": "add_bookmark",
        "payload": {
            "id": shape_id,
            "url": url,
            "x": x,
            "y": y,
            "meta": _semantic_meta(semantic_role, source, confidence, linked_to),
        }
    })
    return f"Bookmarked {url}"


def move_shape(shape_id: str, x: int, y: int) -> str:
    canvas_action_queue.put_nowait({
        "type": "move_shape",
        "payload": {"shapeId": shape_id, "x": x, "y": y}
    })
    return f"Moved {shape_id} to ({x},{y})"


def update_shape(shape_id: str, text: str, color: str) -> str:
    payload: dict = {"shapeId": shape_id}
    if text:
        payload["text"] = text
    if color:
        payload["color"] = _normalize_color(color, "black")
    canvas_action_queue.put_nowait({"type": "update_shape", "payload": payload})
    return f"Updated {shape_id}"


def delete_shapes(shape_ids: list[str]) -> str:
    canvas_action_queue.put_nowait({
        "type": "delete_shapes",
        "payload": {"shapeIds": shape_ids}
    })
    return f"Deleted {len(shape_ids)} shape(s)"


def zoom_to_fit() -> str:
    canvas_action_queue.put_nowait({"type": "zoom_to_fit", "payload": {}})
    return "Zoomed to fit"


def focus_shape(shape_id: str) -> str:
    canvas_action_queue.put_nowait({
        "type": "focus_shape",
        "payload": {"shapeId": shape_id}
    })
    return f"Focused on {shape_id}"


def select_shapes(shape_ids: list[str]) -> str:
    canvas_action_queue.put_nowait({
        "type": "select_shapes",
        "payload": {"shapeIds": shape_ids}
    })
    return f"Selected {len(shape_ids)} shape(s)"


def clear_canvas() -> str:
    canvas_action_queue.put_nowait({"type": "clear_canvas", "payload": {}})
    return "Canvas cleared"


def undo_last_action() -> str:
    """Undo the most recent canvas action the agent or user just made (Ctrl+Z)."""
    canvas_action_queue.put_nowait({"type": "undo"})
    return "Undo applied"


def redo_last_action() -> str:
    """Redo the last undone canvas action (Ctrl+Shift+Z)."""
    canvas_action_queue.put_nowait({"type": "redo"})
    return "Redo applied"
