"""
AlphaSurface — FastAPI WebSocket server + ADK agent orchestrator.

Message flow:
  Browser → WebSocket → main.py → agent.push_audio / push_canvas_image
  Agent tool call → tools.py enqueues → agent._action_drain_loop → broadcast → browser

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

# ── WebSocket registry ────────────────────────────────────────────────────────
connected_clients: list[WebSocket] = []

CANVAS_PASSTHROUGH_TYPES = {
    "add_text", "add_note", "add_geo", "add_arrow",
    "bind_arrow", "add_embed", "add_bookmark",
    "delete_shapes", "update_shape", "move_shape",
    "clear_canvas", "zoom_to_fit", "focus_shape",
    "select_shapes", "ai_interrupted", "ai_status",
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


# ── Agent singleton ───────────────────────────────────────────────────────────
agent = AlphaSurfaceAgent(
    broadcast_fn=broadcast,
    mode=os.environ.get("ALPHASURFACE_MODE", "think"),
    web_search=os.environ.get("ALPHASURFACE_WEB_SEARCH", "false").lower() == "true",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(agent.start())
    yield
    await agent.stop()


app = FastAPI(lifespan=lifespan)

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
    }


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

            # ── Canvas shape inventory (rich: includes bounds) ────────────
            if msg_type == "canvas_snapshot":
                shapes = payload.get("shapes", [])
                shape_count = payload.get("shape_count", 0)
                canvas_tools.update_canvas_state(shapes, shape_count)

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

            # ── Launch config from settings UI ────────────────────────────
            # Sent once when user clicks "Launch" in the config screen.
            # Reconfigures the agent mode and web_search flag.
            elif msg_type == "set_config":
                mode = payload.get("mode", agent.mode)
                web_search = payload.get("webSearch", agent.web_search)
                agent.reconfigure(mode=mode, web_search=web_search)
                print(f"[WS] Config updated: mode={mode} web_search={web_search}")
                await websocket.send_text(json.dumps({
                    "type": "config_ack",
                    "payload": {"mode": mode, "webSearch": web_search}
                }))

            # ── Canvas action passthrough ─────────────────────────────────
            elif msg_type in CANVAS_PASSTHROUGH_TYPES:
                await broadcast(message)

            # ── Local mute toggle — no backend action needed ──────────────
            elif msg_type == "set_audio":
                pass

            else:
                print(f"[WS] Unknown message type: {msg_type!r}")

    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"[WS] Client disconnected ({len(connected_clients)} remaining)")
    except Exception as e:
        print(f"[WS] Error: {e}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)
