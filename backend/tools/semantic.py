from .state import canvas_state, canvas_action_queue

def label_shape(shape_id: str, semantic_role: str) -> str:
    valid_roles = {"main_claim", "evidence", "counterargument",
                   "question", "insight", "definition", "unknown"}
    if semantic_role not in valid_roles:
        return f"Invalid role. Use one of: {', '.join(valid_roles)}"
    canvas_action_queue.put_nowait({
        "type": "label_shape",
        "payload": {"shapeId": shape_id, "semanticRole": semantic_role,
                    "addedBy": "live_agent"}
    })
    return f"Labeled {shape_id} as '{semantic_role}'"


def get_semantic_graph() -> dict:
    shapes = canvas_state["shapes"]
    shape_map = {s.get("id"): s for s in shapes if isinstance(s, dict)}

    nodes = []
    for s in shapes:
        if not isinstance(s, dict) or s.get("type") == "arrow":
            continue
        role = s.get("meta", {}).get("semanticRole", "unknown")
        nodes.append({
            "id": s.get("id"),
            "role": role,
            "text": s.get("text", "")[:100],
            "color": s.get("color", ""),
            "inViewport": s.get("inViewport", True),
        })

    edges = []
    for s in shapes:
        if not isinstance(s, dict) or s.get("type") != "arrow":
            continue
        bindings = s.get("arrowBindings", {})
        src = bindings.get("startShapeId")
        dst = bindings.get("endShapeId")
        if src and dst:
            edges.append({
                "from": src,
                "to": dst,
                "label": s.get("text", ""),
            })

    challenged_ids = {e["to"] for e in edges}
    unchallenged = [
        n for n in nodes
        if n["role"] == "main_claim" and n["id"] not in challenged_ids
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "unchallenged_claims": unchallenged,
        "open_questions": [n for n in nodes if n["role"] == "question"],
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
