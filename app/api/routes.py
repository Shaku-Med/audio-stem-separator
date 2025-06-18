import os
import io
import uuid
import shutil
import tempfile
import zipfile
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from app.core.task_manager import TaskManager
from app.services.audio_separator import AudioSeparator

router = APIRouter()
task_manager = TaskManager()
separator = AudioSeparator()

@router.get("/")
async def root():
    return {
        "message": "Audio Stem Separator API",
        "status": "running",
        "demucs_available": separator.model is not None,
        "device": separator.device
    }

async def process_task(task_id: str):
    task = task_manager.get_task(task_id)
    try:
        temp_dir = tempfile.mkdtemp()
        output_dir = os.path.join(temp_dir, 'stems')
        os.makedirs(output_dir, exist_ok=True)
        
        input_path = os.path.join(temp_dir, task.input_path)
        
        await separator.separate_audio(input_path, output_dir, task_id, task_manager.tasks)
        task.completed_at = datetime.now()
        
    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        raise e

@router.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith('audio/'):
        allowed_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg'}
        if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
            raise HTTPException(
                status_code=400, 
                detail="Invalid file type. Please upload an audio file."
            )
    
    task_id = str(uuid.uuid4())
    
    # Create temporary directory and save file
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, file.filename)
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Create task and add to queue
    task = task_manager.add_task(task_id, input_path)
    
    return {
        "task_id": task_id,
        "status": "queued",
        "queue_position": task.queue_position
    }

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.get("/download/{task_id}")
async def download_stems(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not completed yet")
    
    if not task.stems:
        raise HTTPException(status_code=404, detail="No stems found")
    
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for stem_path in task.stems:
            if os.path.exists(stem_path):
                stem_name = os.path.basename(stem_path)
                zip_file.write(stem_path, stem_name)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        io.BytesIO(zip_buffer.read()),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=stems_{task_id}.zip"}
    )

@router.get("/download/{task_id}/{stem_name}")
async def download_single_stem(task_id: str, stem_name: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task not completed yet")
    
    stem_file = None
    for stem_path in task.stems or []:
        if stem_name in os.path.basename(stem_path):
            stem_file = stem_path
            break
    
    if not stem_file or not os.path.exists(stem_file):
        raise HTTPException(status_code=404, detail="Stem not found")
    
    return FileResponse(
        stem_file,
        media_type="audio/wav",
        filename=os.path.basename(stem_file)
    )

@router.delete("/cleanup/{task_id}")
async def cleanup_task(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.stems:
        for stem_path in task.stems:
            try:
                stem_dir = os.path.dirname(stem_path)
                if os.path.exists(stem_dir):
                    shutil.rmtree(os.path.dirname(stem_dir))
            except Exception as e:
                print(f"Error cleaning up {stem_path}: {e}")
    
    task_manager.cleanup_task(task_id)
    return {"message": "Task cleaned up successfully"}

@router.get("/tasks")
async def list_tasks():
    return task_manager.list_tasks()

@router.get("/queue/status")
async def get_queue_status():
    return task_manager.get_queue_status() 