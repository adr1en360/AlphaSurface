"""
AlphaSurface — FastAPI WebSocket server + ADK agent orchestrator.

Message flow:
  Browser → WebSocket → main.py → agent.push_audio / push_canvas_image
  Agent tool call → tools.py enqueues → agent._action_drain_loop → broadcast → browser

Changes from v1:
  ✅ EventBus wired — canvas changes signal the bus (not timer-based)
  ✅ PersonaAgent started at app startup
  ✅ canvas_snapshot change detection: only signals bus when shape inventory changed
  ✅ set_config reconfigure now properly restarts the session

Run:
  uvicorn main:app --reload --port 8000
"""

import asyncio
import base64
import contextlib
import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from live_session import AlphaSurfaceAgent
from event_bus import get_event_bus
import tools as canvas_tools
from sub_agents.persona_agent import get_persona_agent
from sub_agents import find_empty_note_position
from dispatcher import run_dispatcher, register_handler
from agent_tasks import dispatch
from memory import memory_store

_dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=_dotenv_path)
load_dotenv()

# ── WebSocket registry ────────────────────────────────────────────────────────
connected_clients: list[WebSocket] = []

CANVAS_PASSTHROUGH_TYPES = {
    "add_text", "add_note", "add_geo", "add_arrow",
    "bind_arrow", "add_embed", "add_bookmark",
    "delete_shapes", "update_shape", "move_shape",
    "clear_canvas", "zoom_to_fit", "focus_shape",
    "select_shapes",
    "align_shapes", "distribute_shapes", "resize_shape",
    "create_frame", "group_shapes", "label_shape",
    "add_image",
    "add_research_card", "add_provocation_card", "focus_artifact",
}
CANVAS_PASSTHROUGH_TYPES = {
    "add_text", "add_note", "add_geo", "add_arrow",
    "bind_arrow", "add_embed", "add_bookmark",
    "delete_shapes", "update_shape", "move_shape",
    "clear_canvas", "zoom_to_fit", "focus_shape",
    "select_shapes",
    "align_shapes", "distribute_shapes", "resize_shape",
    "create_frame", "group_shapes", "label_shape",
    "add_image",
    "add_research_card", "add_provocation_card", "focus_artifact",
    "undo", "redo",
}


def _normalize_canvas_action(action: dict) -> dict:
    """Normalize legacy actions into richer semantic action types when possible."""
    if not isinstance(action, dict):
        return action

    if action.get("type") != "add_note":
        return action

    payload = action.get("payload") or {}
    if not isinstance(payload, dict):
        return action

    note_id = str(payload.get("id", ""))
    text = str(payload.get("text", "")).strip()
    color = str(payload.get("color", "")).strip().lower()
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    role = str(meta.get("semanticRole", "")).strip().lower()

    is_status_note = "task_status_" in note_id
    is_candidate = (
        (role == "provocation" or color in {"light-violet", "violet"})
        and text.endswith("?")
        and not is_status_note
    )
    if not is_candidate:
        return action

    return {
        "type": "add_provocation_card",
        "payload": {
            "id": payload.get("id") or f"shape:provocation_{uuid.uuid4().hex[:10]}",
            "x": payload.get("x", 220),
            "y": payload.get("y", 220),
            "text": text,
            "color": color or "light-violet",
            "meta": {
                "semanticRole": "provocation_card",
                "source": meta.get("source", "live_agent"),
                "confidence": float(meta.get("confidence", 0.78)),
                "linked_to": meta.get("linked_to", []),
                "addedBy": meta.get("addedBy", "live_agent"),
            },
        },
    }


async def broadcast(message: dict):
    dead: list[WebSocket] = []
    text = json.dumps(message)
    for ws in connected_clients:
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connected_clients:
            connected_clients.remove(ws)


async def drain_canvas_actions():
    while True:
        try:
            action = canvas_tools.canvas_action_queue.get_nowait()
            action = _normalize_canvas_action(action)
            print(f"[App] Canvas action: {action['type']}")
            await broadcast(action)
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[App] Canvas action drain error: {e}")
            await asyncio.sleep(0.1)


# ── Agent + EventBus singletons ───────────────────────────────────────────────
agent = AlphaSurfaceAgent(
    broadcast_fn=broadcast,
    mode=os.environ.get("ALPHASURFACE_MODE", "think"),
    web_search=os.environ.get("ALPHASURFACE_WEB_SEARCH", "false").lower() == "true",
)

bus = get_event_bus()
persona_agent = get_persona_agent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    subagent_cooldown_until: dict[str, float] = {}

    def _retry_after_seconds(error: Exception) -> float:
        msg = str(error)
        m = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", msg, flags=re.IGNORECASE)
        if not m:
            return 0.0
        try:
            return float(m.group(1))
        except Exception:
            return 0.0

    async def _run_subagent(agent_name: str, payload: dict, run_fn, *extra_args):
        status_shape_id = f"shape:task_status_{uuid.uuid4().hex[:10]}"

        async def _show_status_note(text: str, color: str = "light-violet") -> None:
            note_x, note_y = find_empty_note_position()
            await broadcast({
                "type": "add_note",
                "payload": {
                    "id": status_shape_id,
                    "x": note_x,
                    "y": note_y,
                    "text": text,
                    "color": color,
                    "size": "m",
                },
            })

        async def _clear_status_note() -> None:
            await broadcast({"type": "delete_shapes", "payload": {"shapeIds": [status_shape_id]}})

        now = time.monotonic()
        cooldown_until = subagent_cooldown_until.get(agent_name, 0.0)
        if cooldown_until > now:
            remaining = int(cooldown_until - now)
            await _show_status_note(f"{agent_name} cooling down ({remaining}s)", color="light-red")
            await broadcast({
                "type": "ai_status",
                "payload": {
                    "status": "idle",
                    "subagent": agent_name,
                    "detail": f"{agent_name} cooling down ({remaining}s)",
                },
            })
            await asyncio.sleep(2.0)
            await _clear_status_note()
            return

        await _show_status_note(f"{agent_name} running...")
        await broadcast({
            "type": "ai_status",
            "payload": {
                "status": "thinking",
                "subagent": agent_name,
                "detail": f"{agent_name} running",
            },
        })
        try:
            await run_fn(payload, broadcast, *extra_args)
            await broadcast({
                "type": "ai_status",
                "payload": {
                    "status": "idle",
                    "subagent": agent_name,
                    "detail": f"{agent_name} done",
                },
            })
            await _clear_status_note()
        except Exception as e:
            print(f"[SubAgent:{agent_name}] Error: {e}")
            msg = str(e)
            is_rate_limited = "429" in msg or "RESOURCE_EXHAUSTED" in msg

            if is_rate_limited:
                backoff = max(20.0, _retry_after_seconds(e))
                subagent_cooldown_until[agent_name] = time.monotonic() + backoff
                note_x, note_y = find_empty_note_position()
                await broadcast({
                    "type": "add_note",
                    "payload": {
                        "x": note_x,
                        "y": note_y,
                        "text": f"{agent_name} is temporarily busy. Please retry in about {int(backoff)}s.",
                        "color": "light-red",
                        "size": "m",
                        "meta": {
                            "semanticRole": "error_notice",
                            "source": agent_name,
                            "confidence": 1.0,
                            "linked_to": [],
                            "addedBy": agent_name,
                        },
                    },
                })
                await broadcast({
                    "type": "ai_status",
                    "payload": {
                        "status": "idle",
                        "subagent": agent_name,
                        "detail": f"{agent_name} rate-limited ({int(backoff)}s)",
                    },
                })
                await _clear_status_note()
                return

            note_x, note_y = find_empty_note_position()
            await broadcast({
                "type": "add_note",
                "payload": {
                    "x": note_x,
                    "y": note_y,
                    "text": f"{agent_name} could not finish that request. Try again with a more specific prompt.",
                    "color": "light-red",
                    "size": "m",
                    "meta": {
                        "semanticRole": "error_notice",
                        "source": agent_name,
                        "confidence": 1.0,
                        "linked_to": [],
                        "addedBy": agent_name,
                    },
                },
            })
            await broadcast({
                "type": "ai_status",
                "payload": {
                    "status": "idle",
                    "subagent": agent_name,
                    "detail": f"{agent_name} failed",
                },
            })
            await _clear_status_note()

    # Start event bus monitor
    bus.start()

    # Start persona agent (subscribes to bus events)
    persona_agent.start()

    # Start agent dispatcher (routes tasks from queue to sub-agents)
    dispatcher_task = asyncio.create_task(run_dispatcher())
    canvas_action_task = asyncio.create_task(drain_canvas_actions())

    # Register provocation as a dispatched handler so Live Agent can also trigger it
    async def _provocation_handler(payload: dict):
        await agent._on_provocation_ready()
    register_handler("provocation", _provocation_handler)

    # Register ResearchAgent
    from sub_agents.research_agent import run_research
    async def _research_handler(payload: dict):
        await _run_subagent("research", payload, run_research)
    register_handler("research", _research_handler)

    # Register ImageGenAgent
    from sub_agents.image_gen_agent import run_image_gen
    async def _image_gen_handler(payload: dict):
        await _run_subagent("image_gen", payload, run_image_gen)
    register_handler("image_gen", _image_gen_handler)

    # Register YouTubeAgent
    from sub_agents.youtube_agent import run_youtube
    async def _youtube_handler(payload: dict):
        await _run_subagent("youtube", payload, run_youtube)
    register_handler("youtube", _youtube_handler)

    # Register SuperThinkAgent (reads live canvas_state from tools module)
    from sub_agents.super_think_agent import run_super_think
    async def _super_think_handler(payload: dict):
        await _run_subagent("super_think", payload, run_super_think, canvas_tools.canvas_state)
    register_handler("super_think", _super_think_handler)

    # Register DocumentAgent
    from sub_agents.document_agent import run_document
    async def _document_handler(payload: dict):
        await _run_subagent("document", payload, run_document)
    register_handler("document", _document_handler)

    # Register ContinuationAgent (executes deferred scratch pad tasks)
    from sub_agents.continuation_agent import run as run_continuation
    async def _continuation_handler(payload: dict):
        await _run_subagent("continuation", payload, run_continuation)
    register_handler("continuation", _continuation_handler)

    yield

    # Shutdown
    bus.stop()
    persona_agent.stop()
    await agent.stop()
    dispatcher_task.cancel()
    canvas_action_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await dispatcher_task
    with contextlib.suppress(asyncio.CancelledError):
        await canvas_action_task


app = FastAPI(lifespan=lifespan)

# Serve generated images at /static/images/{filename}
_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent_running": agent.running,
        "mode": agent.mode,
        "web_search": agent.web_search,
        "clients": len(connected_clients),
        "canvas_shapes": canvas_tools.canvas_state["shape_count"],
    }


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    docs_dir = os.path.join(os.path.dirname(__file__), "documents")
    os.makedirs(docs_dir, exist_ok=True)
    file_path = os.path.join(docs_dir, file.filename)
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        print(f"[Upload] Error saving file: {e}")
        return {"status": "error", "message": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"[WS] Client connected ({len(connected_clients)} total)")

    # Sync new client with current canvas state
    if canvas_tools.canvas_state["shape_count"] > 0:
        await websocket.send_text(json.dumps({
            "type": "canvas_snapshot",
            "payload": {
                "shapes": canvas_tools.canvas_state["shapes"],
                "shape_count": canvas_tools.canvas_state["shape_count"],
            },
        }))

    try:
        while True:
            raw = await websocket.receive_text()
            message: dict = json.loads(raw)
            msg_type: str = message.get("type", "")
            payload: dict = message.get("payload", {})

            # ── Canvas shape inventory ────────────────────────────────────
            if msg_type == "canvas_snapshot":
                shapes = payload.get("shapes", [])
                shape_count = payload.get("shape_count", 0)
                viewport = payload.get("viewport", None)
                selected = payload.get("selectedShapeIds", None)
                current_page_id = payload.get("currentPageId")
                current_page_name = payload.get("currentPageName")
                pages = payload.get("pages")
                changed = canvas_tools.update_canvas_state(
                    shapes, shape_count,
                    viewport=viewport,
                    selected_shape_ids=selected,
                    current_page_id=current_page_id,
                    current_page_name=current_page_name,
                    pages=pages,
                )
                if changed:
                    bus.signal_canvas_change()  # ← event-driven, not timer

            # ── Canvas screenshot → Gemini vision ─────────────────────────
            elif msg_type == "canvas_image":
                b64 = payload.get("data", "")
                mime = payload.get("mime", "image/png")
                if b64:
                    agent.push_canvas_image(base64.b64decode(b64), mime)

            # ── Microphone audio ──────────────────────────────────────────
            elif msg_type == "audio_chunk":
                b64 = payload.get("data", "")
                if b64:
                    agent.push_audio(base64.b64decode(b64))
                    # NOTE: bus.signal_audio() is called inside agent.push_audio()

            # ── Launch config from settings UI ────────────────────────────
            elif msg_type == "set_config":
                mode = payload.get("mode", agent.mode)
                web_search = payload.get("webSearch", agent.web_search)
                voice_enabled = bool(payload.get("voiceEnabled", True))
                goal = payload.get("goal")
                audience = payload.get("audience")
                uploaded_file = payload.get("uploadedFile")
                provoc_freq = payload.get("provocationFrequency")
                provoc_style = payload.get("provocationStyle")
                
                # If a goal is provided, inject it into persona memory
                if goal and isinstance(goal, str) and goal.strip():
                    try:
                        mem = memory_store()
                        await mem.merge("user", {"current_focus": goal.strip()})
                        print(f"[WS] Saved user goal to memory: {goal.strip()}")
                    except Exception as e:
                        print(f"[WS] Failed to save goal to memory: {e}")

                # If an audience is provided, inject it into persona memory
                if audience and isinstance(audience, str) and audience.strip():
                    try:
                        mem = memory_store()
                        await mem.merge("user", {"audience": audience.strip()})
                        print(f"[WS] Saved audience to memory: {audience.strip()}")
                    except Exception as e:
                        print(f"[WS] Failed to save audience to memory: {e}")

                try:
                    mem = memory_store()
                    await mem.merge("user", {"mic_enabled": voice_enabled})
                except Exception as e:
                    print(f"[WS] Failed to save mic state to memory: {e}")

                # Save Provocation Settings to memory
                if provoc_freq or provoc_style:
                    try:
                        mem = memory_store()
                        updates = {}
                        if provoc_freq:
                            updates["provocation_frequency"] = provoc_freq
                        if provoc_style:
                            updates["provocation_style"] = provoc_style
                        if updates:
                            await mem.merge("user", updates)
                        print(f"[WS] Saved provocation settings to memory: Freq={provoc_freq}, Style={provoc_style}")
                    except Exception as e:
                        print(f"[WS] Failed to save provocation settings: {e}")

                # If a file was uploaded during onboarding, trigger DocumentAgent
                if uploaded_file and isinstance(uploaded_file, str) and uploaded_file.strip():
                    try:
                        print(f"[WS] Pre-loading document: {uploaded_file.strip()}")
                        dispatch("document", {"query": uploaded_file.strip()}, source="event_bus")
                    except Exception as e:
                        print(f"[WS] Failed to dispatch document agent: {e}")

                await agent.reconfigure(mode=mode, web_search=web_search)
                print(f"[WS] Config updated: mode={mode} web_search={web_search}")
                await websocket.send_text(json.dumps({
                    "type": "config_ack",
                    "payload": {"mode": mode, "webSearch": web_search}
                }))

            # ── Canvas action passthrough (agent → all clients) ───────────
            elif msg_type in CANVAS_PASSTHROUGH_TYPES:
                await broadcast(message)

            # ── Local mute toggle ─────────────────────────────────────────
            elif msg_type == "set_audio":
                is_muted = bool(payload.get("muted", False))
                agent.set_mute_state(is_muted)
                await websocket.send_text(json.dumps({
                    "type": "config_ack",
                    "payload": {"muted": is_muted}
                }))

            # ── Status messages sent by agent — don't re-broadcast ────────
            elif msg_type in {"ai_interrupted", "ai_status", "audio_response", "config_ack"}:
                pass

            else:
                print(f"[WS] Unknown message type: {msg_type!r}")

    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"[WS] Client disconnected ({len(connected_clients)} remaining)")
        if not connected_clients:
            await agent.stop_session()
    except Exception as e:
        print(f"[WS] Error: {e}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)
