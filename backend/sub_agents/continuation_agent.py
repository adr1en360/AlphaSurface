"""
AlphaSurface — ContinuationAgent

A non-live, single-turn ADK agent that picks up deferred canvas instructions
from the scratch pad and executes them while the live model is listening.

Flow:
  1. Live model calls defer_task("instruction")
  2. Instruction lands in scratch pad + dispatcher queue
  3. ContinuationAgent runs runner.run_async() with that instruction
  4. Executes canvas tools AND dispatch tools to completion
  5. Marks task done — live model can check via check_deferred_tasks()
"""

import asyncio

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from model_config import FAST_MODEL
from agent_tasks import mark_deferred_task

_SYSTEM_PROMPT = """\
You are a precise canvas execution agent for AlphaSurface.
You receive a single instruction describing one or more canvas operations to perform.
Execute every part of the instruction using the available tools.

Rules:
- Read canvas state first if you need spatial context
- Use place_in_empty_space or place_near for placement — never hardcode coordinates
- For images: call dispatch_image_gen with a descriptive prompt
- For videos: call dispatch_youtube with a search query
- For research: call dispatch_research with the topic
- Execute everything the instruction asks — do not skip parts
- When all tasks are dispatched and placed, stop
"""

_session_service = InMemorySessionService()
_APP_NAME = "alphasurface_continuation"
_USER_ID = "continuation"


async def run(payload: dict, broadcast_fn) -> None:
    task_id = payload.get("task_id", "unknown")
    instruction = payload.get("instruction", "").strip()

    if not instruction:
        mark_deferred_task(task_id, "failed")
        return

    mark_deferred_task(task_id, "running")
    print(f"[ContinuationAgent] Task {task_id}: {instruction[:80]}")

    try:
        from tools import (
            get_viewport_context, get_canvas_map, get_nearby_shapes,
            get_arrow_connections, get_shapes_in_region, find_shape_by_text,
            get_selected_shapes,
            place_near, place_in_empty_space, place_relative,
            align_shapes, distribute_shapes, stack_shapes,
            resize_shape, rotate_shapes, bring_to_front, send_to_back,
            set_viewport, create_frame, group_shapes,
            label_shape, get_semantic_graph,
            list_canvas_shapes, scan_canvas_text,
            add_text_to_canvas, add_note_to_canvas, add_geo_to_canvas,
            add_arrow_to_canvas, bind_arrow, add_embed_to_canvas,
            add_bookmark_to_canvas, move_shape, update_shape, delete_shapes,
            zoom_to_fit, focus_shape, select_shapes,
            # Dispatch tools — ContinuationAgent CAN dispatch sub-agents
            dispatch_research, dispatch_image_gen, dispatch_youtube,
            dispatch_super_think, dispatch_document,
        )

        # Import draw_freehand if available
        extra_tools = []
        try:
            from tools.pen_draw import draw_freehand
            extra_tools.append(draw_freehand)
        except ImportError:
            pass

        agent = Agent(
            model=FAST_MODEL,
            name="continuation_agent",
            instruction=_SYSTEM_PROMPT,
            tools=[
                get_viewport_context, get_canvas_map, get_nearby_shapes,
                get_arrow_connections, get_shapes_in_region, find_shape_by_text,
                get_selected_shapes,
                place_near, place_in_empty_space, place_relative,
                align_shapes, distribute_shapes, stack_shapes,
                resize_shape, rotate_shapes, bring_to_front, send_to_back,
                set_viewport, create_frame, group_shapes,
                label_shape, get_semantic_graph,
                list_canvas_shapes, scan_canvas_text,
                add_text_to_canvas, add_note_to_canvas, add_geo_to_canvas,
                add_arrow_to_canvas, bind_arrow, add_embed_to_canvas,
                add_bookmark_to_canvas, move_shape, update_shape, delete_shapes,
                zoom_to_fit, focus_shape, select_shapes,
                dispatch_research, dispatch_image_gen, dispatch_youtube,
                dispatch_super_think, dispatch_document,
            ] + extra_tools,
        )

        runner = Runner(
            agent=agent,
            app_name=_APP_NAME,
            session_service=_session_service,
        )

        session_id = f"cont_{task_id}"
        await _session_service.create_session(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            session_id=session_id,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=instruction)],
        )

        async for event in runner.run_async(
            user_id=_USER_ID,
            session_id=session_id,
            new_message=message,
        ):
            calls = event.get_function_calls()
            if calls:
                for call in calls:
                    print(f"[ContinuationAgent] Tool: {call.name}")

        mark_deferred_task(task_id, "done")
        print(f"[ContinuationAgent] Task {task_id} complete")

    except Exception as exc:
        mark_deferred_task(task_id, "failed")
        print(f"[ContinuationAgent] Task {task_id} failed: {exc}")
        import traceback
        traceback.print_exc()
