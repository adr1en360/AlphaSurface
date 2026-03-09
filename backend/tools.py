"""
AlphaSurface — Canvas tool definitions for Gemini Live agent
Each tool receives (name, args, broadcast_fn) and broadcasts the correct JSON payload.
"""

async def add_text_to_canvas(name: str, args: dict, broadcast_fn):
    """Add a text label to the canvas."""
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "text": args.get("text", ""),
            "x": args.get("x"),
            "y": args.get("y"),
            "size": args.get("size", "m"),
            "color": args.get("color", "black"),
        }
    })

async def add_note_to_canvas(name: str, args: dict, broadcast_fn):
    """Add a sticky note to the canvas."""
    await broadcast_fn({
        "type": "add_note",
        "payload": {
            "text": args.get("text", ""),
            "x": args.get("x"),
            "y": args.get("y"),
            "size": args.get("size", "m"),
            "color": args.get("color", "violet"),
        }
    })

async def add_geo_to_canvas(name: str, args: dict, broadcast_fn):
    """Add a geometric shape (rectangle, ellipse, triangle, etc.) to the canvas."""
    await broadcast_fn({
        "type": "add_geo",
        "payload": {
            "geo": args.get("geo", "rectangle"),
            "text": args.get("text", ""),
            "x": args.get("x"),
            "y": args.get("y"),
            "w": args.get("w", 200),
            "h": args.get("h", 120),
            "color": args.get("color", "blue"),
            "fill": args.get("fill", "semi"),
            "dash": args.get("dash", "draw"),
            "size": args.get("size", "m"),
        }
    })

async def bind_arrow(name: str, args: dict, broadcast_fn):
    """Create an arrow connecting two shapes."""
    await broadcast_fn({
        "type": "bind_arrow",
        "payload": {
            "fromShapeId": args.get("fromShapeId"),
            "toShapeId": args.get("toShapeId"),
            "label": args.get("label", ""),
            "color": args.get("color", "black"),
            "size": args.get("size", "m"),
        }
    })

async def delete_shapes(name: str, args: dict, broadcast_fn):
    """Delete specific shapes from the canvas."""
    await broadcast_fn({
        "type": "delete_shapes",
        "payload": {
            "shapeIds": args.get("shapeIds", []),
        }
    })

async def zoom_to_fit(name: str, args: dict, broadcast_fn):
    """Zoom the camera to fit all content on the canvas."""
    await broadcast_fn({
        "type": "zoom_to_fit",
        "payload": {}
    })

async def focus_shape(name: str, args: dict, broadcast_fn):
    """Focus the camera on a specific shape."""
    await broadcast_fn({
        "type": "focus_shape",
        "payload": {
            "shapeId": args.get("shapeId"),
        }
    })

# Tool registry for agent.py to dispatch function calls
TOOLS = {
    "add_text_to_canvas": add_text_to_canvas,
    "add_note_to_canvas": add_note_to_canvas,
    "add_geo_to_canvas": add_geo_to_canvas,
    "bind_arrow": bind_arrow,
    "delete_shapes": delete_shapes,
    "zoom_to_fit": zoom_to_fit,
    "focus_shape": focus_shape,
}

async def dispatch_tool(name: str, args: dict, broadcast_fn):
    """Dispatch a tool call from Gemini to the appropriate handler."""
    if name in TOOLS:
        await TOOLS[name](name, args, broadcast_fn)
    else:
        print(f"Unknown tool: {name}")
