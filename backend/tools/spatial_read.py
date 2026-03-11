import math
from .state import canvas_state

def get_viewport_context() -> dict:
    vp = canvas_state["viewport"]
    shapes = canvas_state["shapes"]

    cx = vp["x"] + vp["w"] / 2
    cy = vp["y"] + vp["h"] / 2

    quadrant_counts = {"top-left": 0, "top-right": 0, "bottom-left": 0, "bottom-right": 0}
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')

    for s in shapes:
        if not isinstance(s, dict):
            continue
        sx, sy = s.get("x", 0), s.get("y", 0)
        sw, sh = s.get("w", 100), s.get("h", 60)
        scx, scy = sx + sw / 2, sy + sh / 2

        min_x = min(min_x, sx)
        min_y = min(min_y, sy)
        max_x = max(max_x, sx + sw)
        max_y = max(max_y, sy + sh)

        if scx < cx and scy < cy:
            quadrant_counts["top-left"] += 1
        elif scx >= cx and scy < cy:
            quadrant_counts["top-right"] += 1
        elif scx < cx and scy >= cy:
            quadrant_counts["bottom-left"] += 1
        else:
            quadrant_counts["bottom-right"] += 1

    empty_quadrants = [q for q, count in quadrant_counts.items() if count == 0]
    
    emptiest = min(quadrant_counts, key=quadrant_counts.get)
    suggestions = {
        "top-left":     (vp["x"] + vp["w"] * 0.25, vp["y"] + vp["h"] * 0.25),
        "top-right":    (vp["x"] + vp["w"] * 0.75, vp["y"] + vp["h"] * 0.25),
        "bottom-left":  (vp["x"] + vp["w"] * 0.25, vp["y"] + vp["h"] * 0.75),
        "bottom-right": (vp["x"] + vp["w"] * 0.75, vp["y"] + vp["h"] * 0.75),
    }
    suggested_x, suggested_y = suggestions[emptiest]

    content_bounds = None
    if shapes:
        content_bounds = {
            "x": int(min_x), "y": int(min_y),
            "w": int(max_x - min_x), "h": int(max_y - min_y)
        }

    return {
        "viewport": vp,
        "center": {"x": int(cx), "y": int(cy)},
        "content_bounds": content_bounds,
        "empty_quadrants": empty_quadrants,
        "shape_density": quadrant_counts,
        "suggested_placement": {"x": int(suggested_x), "y": int(suggested_y)},
        "total_shapes": len(shapes),
        "zoom": vp.get("zoom", 1.0),
    }


def get_canvas_map() -> dict:
    shapes = canvas_state["shapes"]
    if not shapes:
        return {"clusters": [], "isolated_shapes": [], "arrow_graph": {},
                "semantic_summary": {}, "suggested_provocation_target": None}

    arrow_graph = {}  
    for s in shapes:
        if not isinstance(s, dict):
            continue
        if s.get("type") == "arrow":
            bindings = s.get("arrowBindings", {})
            src = bindings.get("startShapeId")
            dst = bindings.get("endShapeId")
            if src and dst:
                arrow_graph.setdefault(src, {"outgoing": [], "incoming": []})
                arrow_graph.setdefault(dst, {"outgoing": [], "incoming": []})
                arrow_graph[src]["outgoing"].append(dst)
                arrow_graph[dst]["incoming"].append(src)

    non_arrow_shapes = [s for s in shapes
                        if isinstance(s, dict) and s.get("type") != "arrow"]

    clusters = []
    visited = set()
    CLUSTER_RADIUS = 400

    for i, shape in enumerate(non_arrow_shapes):
        if shape.get("id") in visited:
            continue
        cluster = [shape]
        visited.add(shape.get("id"))
        sx, sy = shape.get("x", 0) + shape.get("w", 100) / 2, \
                 shape.get("y", 0) + shape.get("h", 60) / 2

        for j, other in enumerate(non_arrow_shapes):
            if other.get("id") in visited:
                continue
            ox, oy = other.get("x", 0) + other.get("w", 100) / 2, \
                     other.get("y", 0) + other.get("h", 60) / 2
            dist = math.sqrt((sx - ox) ** 2 + (sy - oy) ** 2)
            if dist <= CLUSTER_RADIUS:
                cluster.append(other)
                visited.add(other.get("id"))

        all_x = [c.get("x", 0) for c in cluster]
        all_y = [c.get("y", 0) for c in cluster]
        center_x = int(sum(all_x) / len(all_x) + 100)
        center_y = int(sum(all_y) / len(all_y) + 60)

        texts = [c.get("text", "")[:50] for c in cluster if c.get("text")]

        clusters.append({
            "cluster_id": f"cluster_{len(clusters)}",
            "shape_count": len(cluster),
            "shape_ids": [c.get("id") for c in cluster],
            "center": {"x": center_x, "y": center_y},
            "texts": texts[:5],  
        })

    role_counts = {}
    for s in shapes:
        if isinstance(s, dict):
            role = s.get("meta", {}).get("semanticRole", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

    provocation_target = None
    for s in shapes:
        if not isinstance(s, dict) or s.get("type") == "arrow":
            continue
        sid = s.get("id")
        connections = arrow_graph.get(sid, {})
        is_unchallenged = len(connections.get("outgoing", [])) == 0
        in_viewport = s.get("inViewport", True)
        has_text = bool(s.get("text", "").strip())
        if is_unchallenged and in_viewport and has_text:
            provocation_target = {
                "id": sid,
                "text": s.get("text", "")[:100],
                "x": s.get("x"), "y": s.get("y"),
                "reason": "Has no outgoing connections — idea has not been challenged yet"
            }
            break

    return {
        "clusters": clusters,
        "arrow_graph": arrow_graph,
        "semantic_summary": role_counts,
        "suggested_provocation_target": provocation_target,
        "total_shapes": len(shapes),
        "total_arrows": sum(1 for s in shapes
                           if isinstance(s, dict) and s.get("type") == "arrow"),
    }


def get_nearby_shapes(shape_id: str, radius: int) -> dict:
    shapes = canvas_state["shapes"]
    anchor = next((s for s in shapes
                   if isinstance(s, dict) and s.get("id") == shape_id), None)
    if not anchor:
        return {"error": f"Shape {shape_id} not found", "nearby_shapes": []}

    ax = anchor.get("x", 0) + anchor.get("w", 100) / 2
    ay = anchor.get("y", 0) + anchor.get("h", 60) / 2

    nearby = []
    for s in shapes:
        if not isinstance(s, dict) or s.get("id") == shape_id:
            continue
        if s.get("type") == "arrow":
            continue
        sx = s.get("x", 0) + s.get("w", 100) / 2
        sy = s.get("y", 0) + s.get("h", 60) / 2
        dist = math.sqrt((ax - sx) ** 2 + (ay - sy) ** 2)
        if dist <= radius:
            nearby.append({
                "id": s.get("id"),
                "type": s.get("type"),
                "text": s.get("text", "")[:80],
                "distance": int(dist),
                "color": s.get("color", ""),
                "x": s.get("x"), "y": s.get("y"),
            })

    nearby.sort(key=lambda x: x["distance"])

    return {
        "anchor": {
            "id": shape_id,
            "text": anchor.get("text", "")[:80],
            "x": anchor.get("x"), "y": anchor.get("y"),
            "w": anchor.get("w"), "h": anchor.get("h"),
        },
        "nearby_shapes": nearby,
        "count": len(nearby),
        "is_crowded": len(nearby) > 5,
    }


def get_arrow_connections(shape_id: str) -> dict:
    shapes = canvas_state["shapes"]
    shape_map = {s.get("id"): s for s in shapes if isinstance(s, dict)}

    outgoing = []
    incoming = []

    for s in shapes:
        if not isinstance(s, dict) or s.get("type") != "arrow":
            continue
        bindings = s.get("arrowBindings", {})
        src = bindings.get("startShapeId")
        dst = bindings.get("endShapeId")

        if src == shape_id and dst:
            target = shape_map.get(dst, {})
            outgoing.append({
                "arrow_id": s.get("id"),
                "target_id": dst,
                "target_text": target.get("text", "")[:80],
                "arrow_label": s.get("text", ""),
            })
        elif dst == shape_id and src:
            source = shape_map.get(src, {})
            incoming.append({
                "arrow_id": s.get("id"),
                "source_id": src,
                "source_text": source.get("text", "")[:80],
                "arrow_label": s.get("text", ""),
            })

    anchor = shape_map.get(shape_id, {})
    return {
        "shape_id": shape_id,
        "shape_text": anchor.get("text", "")[:80],
        "outgoing": outgoing,
        "incoming": incoming,
        "outgoing_count": len(outgoing),
        "incoming_count": len(incoming),
        "is_isolated": len(outgoing) == 0 and len(incoming) == 0,
        "is_unchallenged": len(outgoing) == 0,
    }


def find_shape_by_text(query: str) -> dict:
    query_lower = query.lower().strip()
    matches = []

    for s in canvas_state["shapes"]:
        if not isinstance(s, dict):
            continue
        text = (s.get("text") or "").lower()
        if query_lower in text:
            score = 2 if text == query_lower else 1
            matches.append({
                "id": s.get("id"),
                "type": s.get("type"),
                "text": s.get("text", "")[:120],
                "color": s.get("color", ""),
                "x": s.get("x"), "y": s.get("y"),
                "inViewport": s.get("inViewport", True),
                "score": score,
            })

    matches.sort(key=lambda x: (-x["score"], x.get("x", 0)))
    return {
        "query": query,
        "matches": matches,
        "count": len(matches),
    }


def get_selected_shapes() -> dict:
    selected_ids = set(canvas_state.get("selected_shape_ids", []))
    if not selected_ids:
        return {"selected": [], "count": 0, "message": "No shapes currently selected"}

    shape_map = {s.get("id"): s for s in canvas_state["shapes"]
                 if isinstance(s, dict)}

    selected = []
    for sid in selected_ids:
        s = shape_map.get(sid)
        if s:
            selected.append({
                "id": s.get("id"),
                "type": s.get("type"),
                "text": s.get("text", "")[:120],
                "color": s.get("color", ""),
                "x": s.get("x"), "y": s.get("y"),
                "w": s.get("w"), "h": s.get("h"),
                "semanticRole": s.get("meta", {}).get("semanticRole", "unknown"),
            })

    return {
        "selected": selected,
        "count": len(selected),
        "ids": list(selected_ids),
    }


def get_shapes_in_region(x: int, y: int, w: int, h: int) -> dict:
    shapes_in_region = []
    for s in canvas_state["shapes"]:
        if not isinstance(s, dict):
            continue
        sx, sy = s.get("x", 0), s.get("y", 0)
        sw, sh = s.get("w", 100), s.get("h", 60)
        
        if (sx < x + w and sx + sw > x and sy < y + h and sy + sh > y):
            shapes_in_region.append({
                "id": s.get("id"),
                "type": s.get("type"),
                "text": s.get("text", "")[:80],
                "color": s.get("color", ""),
                "x": sx, "y": sy,
            })

    return {
        "region": {"x": x, "y": y, "w": w, "h": h},
        "shapes": shapes_in_region,
        "count": len(shapes_in_region),
        "is_empty": len(shapes_in_region) == 0,
    }
