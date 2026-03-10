"""
AlphaSurface — FastAPI WebSocket server + ADK agent orchestrator.

Message flow:
  Browser → WebSocket → main.py → agent.push_audio / push_canvas_image
  Agent tool call → tools.py enqueues action → agent._action_drain_loop
      → broadcast_fn → WebSocket → Browser (tldraw)

Run:
  uvicorn main:app --reload --port 8000
"""

import asyncio
import base64
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from agent import AlphaSurfaceAgent
import tools as canvas_tools

load_dotenv()

# ── WebSocket client registry ─────────────────────────────────────────────────
connected_clients: list[WebSocket] = []
_first_client_connected = asyncio.Event()

async def broadcast(message: dict):
    """Fan-out a message to every connected browser tab."""
    dead: list[WebSocket] = []
    text = json.dumps(message)
    for ws in connected_clients:
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)

# ── Agent singleton ────────────────────────────────────────────────────────────
agent = AlphaSurfaceAgent(
    broadcast_fn=broadcast,
    mode=os.environ.get("ALPHASURFACE_MODE", "think"),
)

# ── App lifecycle ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the ADK agent in the background
    asyncio.create_task(agent.start())
    yield
    await agent.stop()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent_running": agent.running,
        "mode": agent.mode,
        "clients": len(connected_clients),
    }

# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    _first_client_connected.set()
    print(f"[WS] Client connected ({len(connected_clients)} total)")

    # Catch new clients up with current canvas state
    if canvas_tools.canvas_state["shape_count"] > 0:
        await websocket.send_text(json.dumps({
            "type": "canvas_snapshot",
            "payload": {
                "shapeIds": canvas_tools.canvas_state["shape_ids"],
                "shape_count": canvas_tools.canvas_state["shape_count"],
            },
        }))

    try:
        while True:
            raw = await websocket.receive_text()
            message: dict = json.loads(raw)
            msg_type: str = message.get("type", "")
            payload: dict = message.get("payload", {})

            # ── Canvas shape inventory ─────────────────────────────────────
            if msg_type == "canvas_snapshot":
                shape_ids = payload.get("shapeIds", [])
                shape_count = payload.get("shape_count", 0)

                # Update tools.py mirror so bind_arrow etc. use real IDs
                canvas_tools.update_canvas_state(shape_ids, shape_count)

                # Don't rebroadcast snapshots — they're only for backend state tracking

            # ── Canvas screenshot for Gemini vision ───────────────────────
            elif msg_type == "canvas_image":
                jpeg_b64 = payload.get("data", "")
                if jpeg_b64:
                    image_bytes = base64.b64decode(jpeg_b64)
                    agent.push_canvas_image(image_bytes)

            # ── Microphone audio stream ────────────────────────────────────
            elif msg_type == "audio_chunk":
                pcm_b64 = payload.get("data", "")
                if pcm_b64:
                    agent.push_audio(base64.b64decode(pcm_b64))

            # ── Audio on/off toggle from UI ────────────────────────────────
            elif msg_type == "set_audio":
                # No-op — audio is always driven by Gemini Live.
                # Frontend uses this to mute local playback only.
                pass

            # ── Canvas action messages (from test scripts or other tools) ──
            elif msg_type in {
                "add_text", "add_note", "add_geo", "add_arrow",
                "bind_arrow", "add_image", "add_frame", "add_draw",
                "delete_shapes", "update_shape", "move_shape",
                "clear_canvas", "set_camera", "zoom_to_fit",
                "focus_shape", "select_shapes",
            }:
                await broadcast(message)

            else:
                print(f"[WS] Unknown message type: {msg_type!r}")

    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"[WS] Client disconnected ({len(connected_clients)} remaining)")
    except Exception as e:
        print(f"[WS] Error: {e}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)
