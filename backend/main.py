from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Frontend connected!")

    await websocket.send_text(json.dumps({
        "type": "add_text",
        "payload": { "text": "AlphaSurface is alive", "x": 200, "y": 200 }
    }))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            print(f"Received: {message['type']}")

    except WebSocketDisconnect:
        print("Frontend disconnected")

