"""
pen_draw.py — Agent freehand drawing tool
Ported from tldraw PenActionUtil.

Allows the agent to draw freehand strokes on the canvas using a list of
x,y coordinate points. The frontend renders them as tldraw draw shapes.

Usage examples:
  - Sketch a circle around an idea
  - Draw a rough arrow connecting two concepts
  - Annotate a user's freehand drawing
  - Underline important text
  - Draw a diagram outline
"""
import uuid
from .state import canvas_action_queue


def draw_freehand(
    points: str,
    color: str = "black",
    closed: bool = False,
) -> str:
    """
    Draw a freehand stroke on the canvas using a sequence of x,y points.

    points: comma-separated x,y pairs like "100,200,150,220,200,210"
            (every two numbers = one point: x1,y1,x2,y2,x3,y3...)
    color:  stroke color — black | grey | blue | red | green | orange | violet | yellow
    closed: if True, the stroke closes back to the starting point (for shapes like circles)

    Returns the shape ID of the created stroke.

    Examples:
      draw_freehand("100,100,200,100,200,200,100,200", color="blue", closed=True)
        → draws a rough square outline in blue

      draw_freehand("50,300,150,280,250,300,350,280", color="red")
        → draws a wavy line in red

    TIPS:
    - Use ~8-20 points for simple shapes (circle, underline, arrow)
    - Use ~20-50 points for complex shapes
    - For a circle: distribute points evenly around a center
    - For an underline: two points (start_x,y  end_x,y)
    - For a rough arrow: a few points along the shaft + two points for the arrowhead
    """
    _VALID_COLORS = {
        "black", "grey", "gray", "blue", "red", "green",
        "orange", "violet", "yellow", "light-blue", "light-green",
    }
    _COLOR_MAP = {"gray": "grey", "purple": "violet"}
    normalized_color = _COLOR_MAP.get(color.lower(), color.lower())
    if normalized_color not in _VALID_COLORS:
        normalized_color = "black"

    # Parse points string into list of {x, y} dicts
    try:
        nums = [float(n.strip()) for n in points.replace(";", ",").split(",") if n.strip()]
        if len(nums) < 4:
            return "Error: need at least 2 points (4 numbers: x1,y1,x2,y2)"
        # Pair up into points
        point_list = [
            {"x": int(nums[i]), "y": int(nums[i + 1])}
            for i in range(0, len(nums) - 1, 2)
        ]
    except (ValueError, IndexError) as e:
        return f"Error parsing points: {e}. Format: 'x1,y1,x2,y2,x3,y3...'"

    shape_id = f"shape:draw_{uuid.uuid4().hex[:10]}"

    canvas_action_queue.put_nowait({
        "type": "draw_freehand",
        "payload": {
            "id": shape_id,
            "points": point_list,
            "color": normalized_color,
            "closed": bool(closed),
        }
    })

    return f"Freehand stroke drawn with {len(point_list)} points — id={shape_id}"
