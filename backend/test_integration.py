import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_websocket_connection():
    with client.websocket_connect("/ws") as websocket:
        # Send a config update
        websocket.send_json({"type": "set_config", "payload": {"mode": "present", "webSearch": False}})
        
        # We expect a config_ack response
        data = websocket.receive_json()
        assert data["type"] == "config_ack"
        assert data["payload"]["mode"] == "present"

