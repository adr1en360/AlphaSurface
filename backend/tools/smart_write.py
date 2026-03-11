from .state import canvas_state, canvas_action_queue

def place_near(
    anchor_shape_id: str,
    text: str,
    shape_type: str,
    direction: str,
    color: str,
) -> str:
    shapes = canvas_state["shapes"]
    anchor = next((s for s in shapes
                   if isinstance(s, dict) and s.get("id") == anchor_shape_id), None)
    if not anchor:
        return f"Anchor shape {anchor_shape_id} not found — use list_canvas_shapes first"

    ax, ay = anchor.get("x", 300), anchor.get("y", 300)
    aw, ah = anchor.get("w", 200), anchor.get("h", 120)
    GAP = 40
    NEW_W, NEW_H = 220, 120

    if direction == "around":
        sides = {
            "right":  (ax + aw + GAP, ay),
            "below":  (ax, ay + ah + GAP),
            "left":   (ax - NEW_W - GAP, ay),
            "above":  (ax, ay - NEW_H - GAP),
        }
        
        def count_shapes_near(px, py):
            return sum(1 for s in shapes
                      if isinstance(s, dict) and s.get("id") != anchor_shape_id
                      and abs(s.get("x", 0) - px) < 250
                      and abs(s.get("y", 0) - py) < 150)
        direction = min(sides, key=lambda d: count_shapes_near(*sides[d]))

    positions = {
        "right": (ax + aw + GAP, ay + ah // 2 - NEW_H // 2),
        "left":  (ax - NEW_W - GAP, ay + ah // 2 - NEW_H // 2),
        "above": (ax + aw // 2 - NEW_W // 2, ay - NEW_H - GAP),
        "below": (ax + aw // 2 - NEW_W // 2, ay + ah + GAP),
    }
    nx, ny = positions.get(direction, (ax + aw + GAP, ay))
    nx, ny = int(nx), int(ny)

    if shape_type == "note":
        canvas_action_queue.put_nowait({
            "type": "add_note",
            "payload": {"text": text, "x": nx, "y": ny,
                        "color": color or "yellow", "size": "m"}
        })
    elif shape_type == "geo":
        canvas_action_queue.put_nowait({
            "type": "add_geo",
            "payload": {"text": text, "geo": "rectangle",
                        "x": nx, "y": ny, "w": NEW_W, "h": NEW_H,
                        "color": color or "blue", "fill": "semi"}
        })
    else:
        canvas_action_queue.put_nowait({
            "type": "add_text",
            "payload": {"text": text, "x": nx, "y": ny,
                        "color": color or "black", "size": "m"}
        })

    return f"Placed {shape_type} {direction} of {anchor_shape_id} at ({nx},{ny})"


def place_in_empty_space(
    text: str,
    shape_type: str,
    color: str,
    preferred_x: int,
    preferred_y: int,
) -> str:
    vp = canvas_state["viewport"]
    shapes = canvas_state["shapes"]

    if preferred_x == -1:
        preferred_x = int(vp["x"] + vp["w"] * 0.3)
    if preferred_y == -1:
        preferred_y = int(vp["y"] + vp["h"] * 0.3)

    def is_occupied(px, py, pw=220, ph=120):
        for s in shapes:
            if not isinstance(s, dict):
                continue
            sx, sy = s.get("x", 0), s.get("y", 0)
            sw, sh = s.get("w", 200), s.get("h", 120)
            GAP = 30
            if (px < sx + sw + GAP and px + pw > sx - GAP and
                    py < sy + sh + GAP and py + ph > sy - GAP):
                return True
        return False

    x, y = preferred_x, preferred_y
    if not is_occupied(x, y):
        final_x, final_y = x, y
    else:
        found = False
        for step in range(1, 12):
            for dx, dy in [(step * 260, 0), (0, step * 160),
                           (-step * 260, 0), (0, -step * 160),
                           (step * 260, step * 160), (-step * 260, step * 160)]:
                tx, ty = preferred_x + dx, preferred_y + dy
                if not is_occupied(tx, ty):
                     final_x, final_y = tx, ty
                     found = True
                     break
            if found:
                break
        else:
            final_x, final_y = preferred_x + 300, preferred_y + 200

    final_x, final_y = int(final_x), int(final_y)

    if shape_type == "note":
        canvas_action_queue.put_nowait({
            "type": "add_note",
            "payload": {"text": text, "x": final_x, "y": final_y,
                        "color": color or "yellow", "size": "m"}
        })
    elif shape_type == "geo":
        canvas_action_queue.put_nowait({
            "type": "add_geo",
            "payload": {"text": text, "geo": "rectangle",
                        "x": final_x, "y": final_y, "w": 220, "h": 120,
                        "color": color or "blue", "fill": "semi"}
        })
    else:
        canvas_action_queue.put_nowait({
            "type": "add_text",
            "payload": {"text": text, "x": final_x, "y": final_y,
                        "color": color or "black", "size": "m"}
        })

    return f"Placed {shape_type} at ({final_x},{final_y}) — empty space found"
