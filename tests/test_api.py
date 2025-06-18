import pytest
import asyncio
from fastapi.testclient import TestClient
import os
import tempfile
from pathlib import Path
from quickuse import app, tasks, task_queue, active_tasks, SeparationTask

client = TestClient(app)

@pytest.fixture
def test_audio_file():
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        f.write(b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00')
    yield f.name
    os.unlink(f.name)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "status" in data
    assert "demucs_available" in data
    assert "device" in data

def test_upload_endpoint(test_audio_file):
    with open(test_audio_file, 'rb') as f:
        response = client.post(
            "/upload",
            files={"file": ("test.wav", f, "audio/wav")}
        )
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert isinstance(data["task_id"], str)

def test_upload_invalid_file():
    with tempfile.NamedTemporaryFile(suffix='.txt') as f:
        f.write(b'not an audio file')
        f.seek(0)
        response = client.post(
            "/upload",
            files={"file": ("test.txt", f, "text/plain")}
        )
    assert response.status_code == 400

def test_get_task_status(test_audio_file):
    with open(test_audio_file, 'rb') as f:
        upload_response = client.post(
            "/upload",
            files={"file": ("test.wav", f, "audio/wav")}
        )
    task_id = upload_response.json()["task_id"]
    
    response = client.get(f"/status/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "progress" in data

def test_get_nonexistent_task_status():
    response = client.get("/status/nonexistent_task")
    assert response.status_code == 404

def test_list_tasks():
    response = client.get("/tasks")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)

def test_queue_status():
    response = client.get("/queue/status")
    assert response.status_code == 200
    data = response.json()
    assert "queue_length" in data
    assert "active_tasks" in data
    assert isinstance(data["queue_length"], int)
    assert isinstance(data["active_tasks"], list)

def test_cleanup_task(test_audio_file):
    with open(test_audio_file, 'rb') as f:
        upload_response = client.post(
            "/upload",
            files={"file": ("test.wav", f, "audio/wav")}
        )
    task_id = upload_response.json()["task_id"]
    
    response = client.delete(f"/cleanup/{task_id}")
    assert response.status_code == 200
    
    assert task_id not in tasks

def test_cleanup_nonexistent_task():
    response = client.delete("/cleanup/nonexistent_task")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_task_processing():
    task_id = "test_task"
    tasks[task_id] = SeparationTask(
        task_id=task_id,
        status="pending",
        progress=0,
        input_path="test.wav"
    )
    task_queue.append(task_id)
    
    await asyncio.sleep(2)
    
    assert task_id in tasks
    assert tasks[task_id].status in ["processing", "completed", "failed"] 