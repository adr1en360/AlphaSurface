"""
AlphaSurface — ContinuationAgent

A non-live, single-turn ADK agent that picks up deferred canvas instructions
from the scratch pad and executes them while the live model is listening.

Flow:
  1. Live model calls defer_task("place a geo box titled Evaporation near the diagram")
  2. Instruction lands in scratch pad + dispatcher queue
  3. ContinuationAgent runs runner.run_async() with that instruction
  4. Executes canvas tools (add_geo, place_near, etc.) to completion
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
You are a precise canvas action executor for AlphaSurface.

You receive a single instruction describing one canvas operation to perform.
Execute it exactly using the available canvas tools. Nothing more.

Rules:
- Check canvas state first if you need spatial context (list_canvas_shapes or get_canvas_map)
- Always use place_in_empty_space or place_near — never hardcode coordinates
- Execute only what the instruction says — add nothing extra
- One clean action sequence, then stop
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
        # Import tools here — avoids circular imports at module load time
        from tools import (
            get_viewport_context, get_canvas_map, get_nearby_shapes,
            get_arrow_connections, get_shapes_in_region, find_shape_by_text,
            get_selected_shapes, place_near, place_in_empty_space,
            align_shapes, distribute_shapes, resize_shape, create_frame,
            group_shapes, label_shape, get_semantic_graph,
            list_canvas_shapes, scan_canvas_text,
            add_text_to_canvas, add_note_to_canvas, add_geo_to_canvas,
            add_arrow_to_canvas, bind_arrow, add_embed_to_canvas,
            add_bookmark_to_canvas, move_shape, update_shape, delete_shapes,
            zoom_to_fit, focus_shape,
        )

        agent = Agent(
            model=FAST_MODEL,
            name="continuation_agent",
            instruction=_SYSTEM_PROMPT,
            tools=[
                get_viewport_context, get_canvas_map, get_nearby_shapes,
                get_arrow_connections, get_shapes_in_region, find_shape_by_text,
                get_selected_shapes, place_near, place_in_empty_space,
                align_shapes, distribute_shapes, resize_shape, create_frame,
                group_shapes, label_shape, get_semantic_graph,
                list_canvas_shapes, scan_canvas_text,
                add_text_to_canvas, add_note_to_canvas, add_geo_to_canvas,
                add_arrow_to_canvas, bind_arrow, add_embed_to_canvas,
                add_bookmark_to_canvas, move_shape, update_shape, delete_shapes,
                zoom_to_fit, focus_shape,
            ],
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
