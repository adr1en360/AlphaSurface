from .state import canvas_state, canvas_action_queue
import uuid

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

# ── Shape type normalization ───────────────────────────────────────────────────
# Maps anything the model might say to one of our three output types: note/geo/text
_SHAPE_TYPE_MAP = {
    "note": "note",
    "sticky": "note",
    "sticky_note": "note",
    "sticky-note": "note",
    "geo": "geo",
    "rectangle": "geo",
    "rect": "geo",
    "box": "geo",
    "ellipse": "geo",
    "circle": "geo",
    "diamond": "geo",
    "triangle": "geo",
    "cloud": "geo",
    "star": "geo",
    "heart": "geo",
    "hexagon": "geo",
    "shape": "geo",
    "text": "text",
    "label": "text",
}

# ── Local placement registry ──────────────────────────────────────────────────
# Tracks shapes placed in the current session so overlap detection works
# even before the next canvas_snapshot arrives (which takes up to 3 seconds).
# Cleared when canvas_state shape count drops to 0 (canvas cleared).
_local_placed: list[dict] = []


def _clear_local_registry():
    global _local_placed
    _local_placed = []


def _register_local(x: int, y: int, w: int, h: int, shape_id: str):
    _local_placed.append({"id": shape_id, "x": x, "y": y, "w": w, "h": h})


def _all_shapes() -> list[dict]:
    """Combined view: canvas_state shapes + locally placed shapes not yet in state."""
    known_ids = {s.get("id") for s in canvas_state["shapes"] if isinstance(s, dict)}
    local_unseen = [s for s in _local_placed if s["id"] not in known_ids]
    return list(canvas_state["shapes"]) + local_unseen


def _normalize_color(color: str, default: str) -> str:
    c = (color or default).strip().lower().replace("_", "-")
    c = _COLOR_ALIASES.get(c, c)
    return c if c in _VALID_COLORS else default


def _normalize_shape_type(shape_type: str) -> str:
    """Normalize any shape type string to note/geo/text."""
    raw = (shape_type or "geo").strip().lower().replace("-", "_").replace(" ", "_")
    return _SHAPE_TYPE_MAP.get(raw, "geo")


def _new_shape_id(prefix: str) -> str:
    return f"shape:{prefix}_{uuid.uuid4().hex[:10]}"


def _is_occupied(px: int, py: int, pw: int = 220, ph: int = 120, gap: int = 30) -> bool:
    for s in _all_shapes():
        if not isinstance(s, dict):
            continue
        sx, sy = s.get("x", 0), s.get("y", 0)
        sw, sh = s.get("w", 200), s.get("h", 120)
        if (
            px < sx + sw + gap and px + pw > sx - gap and
            py < sy + sh + gap and py + ph > sy - gap
        ):
            return True
    return False


def _find_free_position(preferred_x: int, preferred_y: int,
                        w: int = 220, h: int = 120) -> tuple[int, int]:
    if not _is_occupied(preferred_x, preferred_y, w, h):
        return preferred_x, preferred_y

    for step in range(1, 16):
        candidates = [
            (preferred_x + step * 280, preferred_y),
            (preferred_x, preferred_y + step * 180),
            (preferred_x - step * 280, preferred_y),
            (preferred_x, preferred_y - step * 180),
            (preferred_x + step * 280, preferred_y + step * 180),
            (preferred_x - step * 280, preferred_y + step * 180),
            (preferred_x + step * 280, preferred_y - step * 180),
            (preferred_x - step * 280, preferred_y - step * 180),
        ]
        for tx, ty in candidates:
            if not _is_occupied(tx, ty, w, h):
                return int(tx), int(ty)

    return preferred_x + 340, preferred_y + 240


def _resolve_shape_id(raw_id: str) -> str:
    """Ensure shape ID has shape: prefix for lookup."""
    if not raw_id:
        return raw_id
    return raw_id if raw_id.startswith("shape:") else f"shape:{raw_id}"


def _find_anchor(anchor_shape_id: str) -> dict | None:
    """Find anchor shape, tolerating IDs with or without 'shape:' prefix."""
    full_id = _resolve_shape_id(anchor_shape_id)
    for s in _all_shapes():
        if not isinstance(s, dict):
            continue
        sid = s.get("id", "")
        if sid == full_id or sid == anchor_shape_id:
            return s
    return None


def _emit_shape(shape_type: str, text: str, x: int, y: int,
                w: int, h: int, color: str, geo_type: str = "rectangle") -> str:
    """Queue a canvas action and register in local placement registry."""
    shape_id = _new_shape_id(shape_type)

    if shape_type == "note":
        normalized_color = _normalize_color(color, "yellow")
        canvas_action_queue.put_nowait({
            "type": "add_note",
            "payload": {
                "id": shape_id,
                "text": text, "x": x, "y": y,
                "color": normalized_color, "size": "m",
            },
        })
        _register_local(x, y, w, h, shape_id)

    elif shape_type == "geo":
        normalized_color = _normalize_color(color, "blue")
        canvas_action_queue.put_nowait({
            "type": "add_geo",
            "payload": {
                "id": shape_id,
                "text": text, "geo": geo_type,
                "x": x, "y": y, "w": w, "h": h,
                "color": normalized_color, "fill": "semi",
            },
        })
        _register_local(x, y, w, h, shape_id)

    else:  # text
        normalized_color = _normalize_color(color, "black")
        canvas_action_queue.put_nowait({
            "type": "add_text",
            "payload": {
                "id": shape_id,
                "text": text, "x": x, "y": y,
                "color": normalized_color, "size": "m",
            },
        })
        _register_local(x, y, 260, 60, shape_id)

    return shape_id


def place_in_empty_space(
    text: str,
    shape_type: str,
    color: str,
    preferred_x: int,
    preferred_y: int,
) -> str:
    """
    Place a shape in empty space near a preferred position.
    Uses both canvas_state and locally-placed shapes to avoid overlap.
    Returns the shape ID so the agent can reference it later (e.g. for bind_arrow).
    """
    # Clear local registry if canvas was cleared
    if canvas_state["shape_count"] == 0 and not _local_placed:
        _clear_local_registry()

    vp = canvas_state["viewport"]
    if int(preferred_x) <= 0:
        preferred_x = int(vp["x"] + vp["w"] * 0.3)
    if int(preferred_y) <= 0:
        preferred_y = int(vp["y"] + vp["h"] * 0.3)

    normalized_type = _normalize_shape_type(shape_type)
    w, h = (280, 180) if normalized_type == "note" else (220, 120)

    final_x, final_y = _find_free_position(int(preferred_x), int(preferred_y), w, h)

    # Extract geo sub-type if model passed e.g. "ellipse", "diamond"
    raw = (shape_type or "geo").strip().lower()
    geo_subtype = raw if raw in {
        "rectangle", "ellipse", "triangle", "diamond",
        "cloud", "star", "heart", "hexagon", "pentagon", "octagon"
    } else "rectangle"

    shape_id = _emit_shape(normalized_type, text, final_x, final_y, w, h, color, geo_subtype)
    return f"Placed {normalized_type} at ({final_x},{final_y}) id={shape_id}"


def place_near(
    anchor_shape_id: str,
    text: str,
    shape_type: str,
    direction: str,
    color: str,
) -> str:
    """
    Place a shape adjacent to an existing shape.
    direction: right | left | above | below | around (auto-picks emptiest side)
    Returns the shape ID.
    """
    anchor = _find_anchor(anchor_shape_id)
    if not anchor:
        # Fallback to empty space placement if anchor not found
        vp = canvas_state["viewport"]
        return place_in_empty_space(
            text, shape_type, color,
            int(vp["x"] + vp["w"] * 0.4),
            int(vp["y"] + vp["h"] * 0.4),
        )

    ax, ay = int(anchor.get("x", 300)), int(anchor.get("y", 300))
    aw, ah = int(anchor.get("w", 220)), int(anchor.get("h", 120))
    GAP = 40
    normalized_type = _normalize_shape_type(shape_type)
    W, H = (280, 180) if normalized_type == "note" else (220, 120)

    # Auto-pick direction based on which side has fewest shapes
    if direction == "around":
        all_s = _all_shapes()
        def density(px, py):
            return sum(1 for s in all_s
                      if isinstance(s, dict) and s.get("id") != anchor.get("id")
                      and abs(s.get("x", 0) - px) < 280
                      and abs(s.get("y", 0) - py) < 180)

        candidates = {
            "right": (ax + aw + GAP, ay + ah // 2 - H // 2),
            "below": (ax + aw // 2 - W // 2, ay + ah + GAP),
            "left":  (ax - W - GAP, ay + ah // 2 - H // 2),
            "above": (ax + aw // 2 - W // 2, ay - H - GAP),
        }
        direction = min(candidates, key=lambda d: density(*candidates[d]))

    # Compute position centered on the chosen side
    positions = {
        "right": (ax + aw + GAP,          ay + ah // 2 - H // 2),
        "left":  (ax - W - GAP,            ay + ah // 2 - H // 2),
        "above": (ax + aw // 2 - W // 2,  ay - H - GAP),
        "below": (ax + aw // 2 - W // 2,  ay + ah + GAP),
    }
    nx, ny = positions.get(direction, (ax + aw + GAP, ay))

    # If that position is occupied, find nearest free spot from there
    if _is_occupied(nx, ny, W, H):
        nx, ny = _find_free_position(nx, ny, W, H)

    nx, ny = int(nx), int(ny)
    shape_id = _emit_shape(normalized_type, text, nx, ny, W, H, color)
    return f"Placed {normalized_type} {direction} of {anchor_shape_id} at ({nx},{ny}) id={shape_id}"


def place_relative(
    anchor_shape_id: str,
    text: str,
    shape_type: str,
    side: str,
    align: str,
    color: str,
    side_offset: int = 20,
    align_offset: int = 0,
) -> str:
    """
    Precise placement relative to another shape — ported from tldraw PlaceActionUtil.
    side:  right | left | top | bottom
    align: start | center | end
    Returns the shape ID.

    Example: place_relative(anchor_id, "Step 2", "geo", "right", "center", "blue")
    → places the new shape directly to the right of the anchor, vertically centered.
    """
    anchor = _find_anchor(anchor_shape_id)
    if not anchor:
        return place_in_empty_space(text, shape_type, color, 300, 300)

    ax = int(anchor.get("x", 0))
    ay = int(anchor.get("y", 0))
    aw = int(anchor.get("w", 220))
    ah = int(anchor.get("h", 120))
    normalized_type = _normalize_shape_type(shape_type)
    W, H = (280, 180) if normalized_type == "note" else (220, 120)
    so = int(side_offset)
    ao = int(align_offset)

    if side == "right":
        nx = ax + aw + so
        if align == "start":   ny = ay + ao
        elif align == "end":   ny = ay + ah - H - ao
        else:                  ny = ay + ah // 2 - H // 2 + ao  # center

    elif side == "left":
        nx = ax - W - so
        if align == "start":   ny = ay + ao
        elif align == "end":   ny = ay + ah - H - ao
        else:                  ny = ay + ah // 2 - H // 2 + ao

    elif side == "top":
        ny = ay - H - so
        if align == "start":   nx = ax + ao
        elif align == "end":   nx = ax + aw - W - ao
        else:                  nx = ax + aw // 2 - W // 2 + ao

    elif side == "bottom":
        ny = ay + ah + so
        if align == "start":   nx = ax + ao
        elif align == "end":   nx = ax + aw - W - ao
        else:                  nx = ax + aw // 2 - W // 2 + ao

    else:
        nx, ny = ax + aw + so, ay

    nx, ny = int(nx), int(ny)
    if _is_occupied(nx, ny, W, H):
        nx, ny = _find_free_position(nx, ny, W, H)

    shape_id = _emit_shape(normalized_type, text, nx, ny, W, H, color)
    return f"Placed {normalized_type} at {side}/{align} of {anchor_shape_id} at ({nx},{ny}) id={shape_id}"
