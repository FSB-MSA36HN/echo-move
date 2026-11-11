import json

import pytest
from fastapi.testclient import TestClient

from echo_move.app import create_app
from echo_move.config import Settings
from echo_move.matlab_bridge import MatlabBridge


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHO_DEMO_MODE", "1")
    monkeypatch.setenv("ECHO_MATLAB_DIR", str(tmp_path))
    with TestClient(create_app(Settings())) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["demo_mode"] is True


def test_matlab_iqa_missing(client):
    assert client.get("/matlab_iqa").json() == {"available": False}


def test_matlab_iqa_present(client, tmp_path):
    (tmp_path / "x_iqa.json").write_text(json.dumps({"summary": {"overall": 77}}))
    body = client.get("/matlab_iqa").json()
    assert body["available"] and body["overall"] == 77


def test_ws_demo_frame(client):
    with client.websocket_connect("/ws/pose") as ws:
        ws.send_text("{}")
        msg = json.loads(ws.receive_text())
    assert msg["mode"] == "DEMO" and "persons" in msg


def test_bridge_tolerates_partial_write(tmp_path):
    (tmp_path / "a_iqa.json").write_text("{not json")
    assert MatlabBridge(tmp_path).read() is None
