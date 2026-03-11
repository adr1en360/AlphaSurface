from .state import canvas_state, canvas_action_queue
from memory import memory_store

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


def add_text_to_canvas(text: str, x: int, y: int, color: str, size: str) -> str:
    if size not in ["s", "m", "l", "xl"]:
        size = "m"
    canvas_action_queue.put_nowait({
        "type": "add_text",
        "payload": {"text": text, "x": x, "y": y,
                    "color": color or "black", "size": size}
    })
    return f"Text placed at ({x},{y})"


def add_note_to_canvas(text: str, x: int, y: int, color: str, size: str) -> str:
    if size not in ["s", "m", "l", "xl"]:
        size = "m"
    canvas_action_queue.put_nowait({
        "type": "add_note",
        "payload": {"text": text, "x": x, "y": y,
                    "color": color or "yellow", "size": size}
    })
    return f"Note placed at ({x},{y})"


def add_geo_to_canvas(text: str, geo: str, x: int, y: int,
                      w: int, h: int, color: str, fill: str) -> str:
    canvas_action_queue.put_nowait({
        "type": "add_geo",
        "payload": {
            "text": text, "geo": geo or "rectangle",
            "x": x, "y": y, "w": w or 200, "h": h or 120,
            "color": color or "blue", "fill": fill or "semi"
        }
    })
    return f"{geo} at ({x},{y})"


def add_arrow_to_canvas(x1: int, y1: int, x2: int, y2: int,
                        label: str, color: str) -> str:
    canvas_action_queue.put_nowait({
        "type": "add_arrow",
        "payload": {"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "label": label or "", "color": color or "black"}
    })
    return f"Arrow ({x1},{y1})→({x2},{y2})"


def bind_arrow(from_shape_id: str, to_shape_id: str,
               label: str, color: str) -> str:
    canvas_action_queue.put_nowait({
        "type": "bind_arrow",
        "payload": {"fromShapeId": from_shape_id, "toShapeId": to_shape_id,
                    "label": label or "", "color": color or "black"}
    })
    return f"Bound arrow {from_shape_id}→{to_shape_id}"


def add_embed_to_canvas(url: str, x: int, y: int, w: int, h: int) -> str:
    canvas_action_queue.put_nowait({
        "type": "add_embed",
        "payload": {"url": url, "x": x, "y": y, "w": w or 560, "h": h or 315}
    })
    return f"Embedded {url}"


def add_bookmark_to_canvas(url: str, x: int, y: int) -> str:
    canvas_action_queue.put_nowait({
        "type": "add_bookmark",
        "payload": {"url": url, "x": x, "y": y}
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
        payload["color"] = color
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
