from .state import canvas_action_queue

def align_shapes(shape_ids: list[str], alignment: str) -> str:
    if len(shape_ids) < 2:
        return "Need at least 2 shapes to align"
    canvas_action_queue.put_nowait({
        "type": "align_shapes",
        "payload": {"shapeIds": shape_ids, "alignment": alignment}
    })
    return f"Aligned {len(shape_ids)} shapes: {alignment}"


def distribute_shapes(shape_ids: list[str], direction: str) -> str:
    if len(shape_ids) < 3:
        return "Need at least 3 shapes to distribute"
    canvas_action_queue.put_nowait({
        "type": "distribute_shapes",
        "payload": {"shapeIds": shape_ids, "direction": direction}
    })
    return f"Distributed {len(shape_ids)} shapes: {direction}"


def resize_shape(shape_id: str, w: int, h: int) -> str:
    canvas_action_queue.put_nowait({
        "type": "resize_shape",
        "payload": {"shapeId": shape_id, "w": w, "h": h}
    })
    return f"Resized {shape_id} to {w}x{h}"


def create_frame(x: int, y: int, w: int, h: int, label: str) -> str:
    canvas_action_queue.put_nowait({
        "type": "create_frame",
        "payload": {"x": x, "y": y, "w": w, "h": h, "label": label}
    })
    return f"Frame '{label}' created at ({x},{y}) size {w}x{h}"


def group_shapes(shape_ids: list[str]) -> str:
    if len(shape_ids) < 2:
        return "Need at least 2 shapes to group"
    canvas_action_queue.put_nowait({
        "type": "group_shapes",
        "payload": {"shapeIds": shape_ids}
    })
    return f"Grouped {len(shape_ids)} shapes"
