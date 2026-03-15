from .state import canvas_action_queue


def align_shapes(shape_ids: list[str], alignment: str) -> str:
    """
    Align shapes to each other.
    alignment: left | center-horizontal | right | top | center-vertical | bottom
    """
    if len(shape_ids) < 2:
        return "Need at least 2 shapes to align"
    canvas_action_queue.put_nowait({
        "type": "align_shapes",
        "payload": {"shapeIds": shape_ids, "alignment": alignment}
    })
    return f"Aligned {len(shape_ids)} shapes: {alignment}"


def distribute_shapes(shape_ids: list[str], direction: str) -> str:
    """
    Distribute shapes with equal spacing between them.
    direction: horizontal | vertical
    """
    if len(shape_ids) < 3:
        return "Need at least 3 shapes to distribute"
    canvas_action_queue.put_nowait({
        "type": "distribute_shapes",
        "payload": {"shapeIds": shape_ids, "direction": direction}
    })
    return f"Distributed {len(shape_ids)} shapes: {direction}"


def stack_shapes(shape_ids: list[str], direction: str, gap: int = 20) -> str:
    """
    Stack shapes with equal spacing (like distribute but tighter control).
    direction: horizontal | vertical
    gap: spacing between shapes in pixels (default 20)
    """
    if len(shape_ids) < 2:
        return "Need at least 2 shapes to stack"
    canvas_action_queue.put_nowait({
        "type": "stack_shapes",
        "payload": {"shapeIds": shape_ids, "direction": direction, "gap": int(gap)}
    })
    return f"Stacked {len(shape_ids)} shapes: {direction} gap={gap}"


def resize_shape(shape_id: str, w: int, h: int) -> str:
    """Resize a shape to exact pixel dimensions."""
    canvas_action_queue.put_nowait({
        "type": "resize_shape",
        "payload": {"shapeId": shape_id, "w": w, "h": h}
    })
    return f"Resized {shape_id} to {w}x{h}"


def rotate_shapes(shape_ids: list[str], degrees: float,
                  origin_x: int = 0, origin_y: int = 0) -> str:
    """
    Rotate shapes by a given number of degrees around an origin point.
    degrees: rotation amount (positive = clockwise)
    origin_x/y: center of rotation (defaults to 0,0 which tldraw handles as shape center)
    """
    canvas_action_queue.put_nowait({
        "type": "rotate_shapes",
        "payload": {
            "shapeIds": shape_ids,
            "degrees": float(degrees),
            "originX": int(origin_x),
            "originY": int(origin_y),
        }
    })
    return f"Rotated {len(shape_ids)} shapes by {degrees}°"


def bring_to_front(shape_ids: list[str]) -> str:
    """Bring shapes to the front of the z-order (on top of everything else)."""
    canvas_action_queue.put_nowait({
        "type": "bring_to_front",
        "payload": {"shapeIds": shape_ids}
    })
    return f"Brought {len(shape_ids)} shapes to front"


def send_to_back(shape_ids: list[str]) -> str:
    """Send shapes to the back of the z-order (behind everything else)."""
    canvas_action_queue.put_nowait({
        "type": "send_to_back",
        "payload": {"shapeIds": shape_ids}
    })
    return f"Sent {len(shape_ids)} shapes to back"


def set_viewport(x: int, y: int, w: int, h: int) -> str:
    """
    Move the canvas camera to show a specific area.
    Use this to navigate to a region of the canvas before working on it,
    or to show the user something specific.
    x, y: top-left corner of the area to show
    w, h: width and height of the area
    """
    canvas_action_queue.put_nowait({
        "type": "set_viewport",
        "payload": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
    })
    return f"Viewport moved to ({x},{y}) size {w}x{h}"


def create_frame(x: int, y: int, w: int, h: int, label: str) -> str:
    """Create a named frame (container) on the canvas."""
    canvas_action_queue.put_nowait({
        "type": "create_frame",
        "payload": {"x": x, "y": y, "w": w, "h": h, "label": label}
    })
    return f"Frame '{label}' created at ({x},{y}) size {w}x{h}"


def group_shapes(shape_ids: list[str]) -> str:
    """Group multiple shapes together so they move as one."""
    if len(shape_ids) < 2:
        return "Need at least 2 shapes to group"
    canvas_action_queue.put_nowait({
        "type": "group_shapes",
        "payload": {"shapeIds": shape_ids}
    })
    return f"Grouped {len(shape_ids)} shapes"
