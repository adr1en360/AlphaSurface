"""
AlphaSurface — ADK Live agent setup.
"""

from google.adk.agents import LlmAgent
import tools as canvas_tools
from model_config import LIVE_MODEL
from prompts.loader import build_system_prompt
from tools import (
    think, todo_update,
    get_viewport_context, list_canvas_shapes, scan_canvas_text,
    find_shape_by_text, get_selected_shapes,
    place_near, place_in_empty_space,
    add_note_to_canvas, add_geo_to_canvas, add_arrow_to_canvas,
    bind_arrow, move_shape, update_shape, delete_shapes,
    align_shapes, distribute_shapes, stack_shapes,
    zoom_to_fit, memory_read, memory_write,
    dispatch_research, dispatch_image_gen, dispatch_youtube,
    dispatch_super_think, defer_task, check_deferred_tasks,
)

LIVE_AGENT_TOOLS = [
    think, todo_update,
    get_viewport_context, list_canvas_shapes, scan_canvas_text,
    find_shape_by_text, get_selected_shapes,
    place_near, place_in_empty_space,
    add_note_to_canvas, add_geo_to_canvas, add_arrow_to_canvas,
    bind_arrow, move_shape, update_shape, delete_shapes,
    align_shapes, distribute_shapes, stack_shapes,
    zoom_to_fit, memory_read, memory_write,
    dispatch_research, dispatch_image_gen, dispatch_youtube,
    dispatch_super_think, defer_task, check_deferred_tasks,
]

def create_agent(
    mode: str = "think",
    web_search: bool = False,
    persona: dict | None = None,
    model_name: str | None = None,
) -> LlmAgent:
    tools = list(LIVE_AGENT_TOOLS)
    return LlmAgent(
        name="AlphaSurface",
        model=model_name or LIVE_MODEL,
        description="Real-time voice+vision whiteboard co-thinker",
        instruction=build_system_prompt(mode, web_search, persona),
        tools=tools,
    )
