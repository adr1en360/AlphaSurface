from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track all connected clients
connected_clients: list[WebSocket] = []

async def broadcast(message: dict):
    for client in connected_clients:
        await client.send_text(json.dumps(message))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"Client connected. Total: {len(connected_clients)}")

    await websocket.send_text(json.dumps({
        "type": "add_text",
        "payload": { "text": "AlphaSurface is alive", "x": 200, "y": 200 }
    }))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            print(f"Received: {message['type']} — broadcasting to {len(connected_clients)} clients")
            await broadcast(message)

    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"Client disconnected. Total: {len(connected_clients)}")
        # ========== TEST CONNECTION CODE - END ==========

