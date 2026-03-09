from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import json
import asyncio
import base64
import os
from agent import AlphaSurfaceAgent

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Connected clients ─────────────────────────────────────────────────────────
connected_clients: list[WebSocket] = []

async def broadcast(message: dict):
    """Send a message to every connected client."""
    disconnected = []
    for client in connected_clients:
        try:
            await client.send_text(json.dumps(message))
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        connected_clients.remove(client)

# ── Canvas state (kept in memory, updated by snapshots) ──────────────────────
canvas_state = {
    "shape_ids": [],
    "shape_count": 0,
    "last_jpeg": None,   # bytes — latest canvas screenshot from browser
}

# ── Agent instance ────────────────────────────────────────────────────────────
agent = AlphaSurfaceAgent(broadcast_fn=broadcast, mode=os.environ.get("ALPHASURFACE_MODE", "think"))

# ── Startup event ─────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(agent.start())

# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"Client connected. Total: {len(connected_clients)}")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            payload = message.get("payload", {})

            # ── Canvas snapshot from browser ──────────────────────────────────
            if msg_type == "canvas_snapshot":
                canvas_state["shape_ids"] = payload.get("shapeIds", [])
                canvas_state["shape_count"] = payload.get("shape_count", 0)
                print(f"Canvas: {canvas_state['shape_count']} shapes | IDs: {canvas_state['shape_ids']}")
                # Broadcast back so test scripts and agent can read real IDs
                await broadcast(message)

            # ── Canvas JPEG screenshot from browser (for Gemini vision) ───────
            elif msg_type == "canvas_image":
                jpeg_b64 = payload.get("data", "")
                if jpeg_b64:
                    canvas_state["last_jpeg"] = base64.b64decode(jpeg_b64)
                    print(f"Canvas image received: {len(canvas_state['last_jpeg'])} bytes")
                    # Push to agent vision queue when agent is running
                    agent.push_canvas_image(canvas_state["last_jpeg"])

            # ── Audio chunk from browser microphone (for Gemini hearing) ──────
            elif msg_type == "audio_chunk":
                pcm_b64 = payload.get("data", "")
                if pcm_b64:
                    pcm_bytes = base64.b64decode(pcm_b64)
                    # Push to agent audio queue when agent is running
                    agent.push_audio(pcm_bytes)

            # ── All canvas action messages — broadcast to all clients ─────────
            # These come from test scripts or will come from agent.py
            elif msg_type in (
                "add_text", "add_note", "add_geo", "add_arrow",
                "bind_arrow", "add_image", "add_frame", "add_draw",
                "delete_shapes", "update_shape", "move_shape",
                "clear_canvas", "set_camera", "zoom_to_fit",
                "focus_shape", "select_shapes",
            ):
                print(f"Action: {msg_type} → broadcasting to {len(connected_clients)} clients")
                await broadcast(message)

            else:
                print(f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"Client disconnected. Total: {len(connected_clients)}")

# ── Helper for agent.py to broadcast canvas actions ──────────────────────────
# agent.py imports this function directly
async def send_to_canvas(message: dict):
    """Called by agent.py to place shapes on the canvas."""
    await broadcast(message)

# ── Canvas state reader for agent.py ─────────────────────────────────────────
def get_canvas_state() -> dict:
    """Called by agent.py to know what's currently on the canvas."""
    return canvas_state