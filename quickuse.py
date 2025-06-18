#!/usr/bin/env python3

import os
import io
import uuid
import asyncio
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Dict
import shutil
from collections import deque
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import librosa
import soundfile as sf
import numpy as np

try:
    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    DEMUCS_AVAILABLE = True
except ImportError:
    DEMUCS_AVAILABLE = False

app = FastAPI(
    title="Audio Stem Separator API",
    description="Upload audio files and get separated stems (vocals, drums, bass, guitar, piano, other)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SeparationTask(BaseModel):
    task_id: str
    status: str
    progress: int
    stems: Optional[List[str]] = None
    error: Optional[str] = None
    queue_position: Optional[int] = None
    created_at: datetime = datetime.now()
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    input_path: Optional[str] = None

class AudioSeparator:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.model_name = "htdemucs"
        
        if DEMUCS_AVAILABLE:
            self.load_model()
    
    def load_model(self):
        try:
            print(f"Loading model: {self.model_name}")
            self.model = get_model(self.model_name)
            self.model.to(self.device)
            print(f"Model loaded on {self.device}")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None
    
    async def separate_audio(self, audio_path: str, output_dir: str, task_id: str):
        try:
            if not DEMUCS_AVAILABLE or self.model is None:
                return await self.simple_separation(audio_path, output_dir, task_id)
            
            tasks[task_id].progress = 20
            
            audio, sr = librosa.load(audio_path, sr=None, mono=False)
            
            if audio.ndim == 1:
                audio = np.stack([audio, audio])
            
            audio_tensor = torch.from_numpy(audio).float().to(self.device)
            if audio_tensor.dim() == 2:
                audio_tensor = audio_tensor.unsqueeze(0)
            
            tasks[task_id].progress = 50
            
            with torch.no_grad():
                separated = apply_model(self.model, audio_tensor, device=self.device)
            
            tasks[task_id].progress = 80
            
            stem_files = []
            stem_names = self.model.sources
            
            for i, stem_name in enumerate(stem_names):
                stem_audio = separated[0, i].cpu().numpy()
                stem_file = os.path.join(output_dir, f"{stem_name}.wav")
                sf.write(stem_file, stem_audio.T, sr)
                stem_files.append(stem_file)
            
            tasks[task_id].progress = 100
            tasks[task_id].status = "completed"
            tasks[task_id].stems = stem_files
            
            return stem_files
            
        except Exception as e:
            tasks[task_id].status = "failed"
            tasks[task_id].error = str(e)
            raise e
    
    async def simple_separation(self, audio_path: str, output_dir: str, task_id: str):
        try:
            tasks[task_id].progress = 30
            
            audio, sr = librosa.load(audio_path, sr=None, mono=False)
            
            if audio.ndim == 1:
                audio = np.stack([audio, audio])
            
            tasks[task_id].progress = 60
            
            stems = {}
            
            vocals = (audio[0] + audio[1]) / 2
            stems['vocals'] = vocals
            
            instrumental = audio[0] - audio[1]
            stems['other'] = instrumental
            
            drums = self.extract_drums(audio, sr)
            stems['drums'] = drums
            
            bass = self.extract_bass(audio, sr)
            stems['bass'] = bass
            
            tasks[task_id].progress = 90
            
            stem_files = []
            for stem_name, stem_audio in stems.items():
                stem_file = os.path.join(output_dir, f"{stem_name}.wav")
                sf.write(stem_file, stem_audio, sr)
                stem_files.append(stem_file)
            
            tasks[task_id].progress = 100
            tasks[task_id].status = "completed"
            tasks[task_id].stems = stem_files
            
            return stem_files
            
        except Exception as e:
            tasks[task_id].status = "failed"
            tasks[task_id].error = str(e)
            raise e
    
    def extract_drums(self, audio, sr):
        hop_length = 512
        frame_length = 2048
        
        onset_frames = librosa.onset.onset_detect(
            y=audio.mean(axis=0), sr=sr, hop_length=hop_length
        )
        
        drum_mask = np.zeros(audio.shape[1])
        for frame in onset_frames:
            start = max(0, frame * hop_length - 1024)
            end = min(len(drum_mask), frame * hop_length + 1024)
            drum_mask[start:end] = 1
        
        return audio.mean(axis=0) * drum_mask
    
    def extract_bass(self, audio, sr):
        from scipy import signal
        
        nyquist = sr / 2
        cutoff = 250 / nyquist
        b, a = signal.butter(4, cutoff, btype='low')
        
        mono_audio = audio.mean(axis=0)
        bass = signal.filtfilt(b, a, mono_audio)
        
        return bass

separator = AudioSeparator()
tasks = {}

MAX_CONCURRENT_TASKS = 2
task_queue = deque()
active_tasks: Dict[str, asyncio.Task] = {}

@app.get("/")
async def root():
    return {
        "message": "Audio Stem Separator API",
        "status": "running",
        "demucs_available": DEMUCS_AVAILABLE,
        "device": separator.device if separator else "none"
    }

async def process_queue():
    while True:
        if len(active_tasks) < MAX_CONCURRENT_TASKS and task_queue:
            task_id = task_queue.popleft()
            task = tasks[task_id]
            task.status = "processing"
            task.started_at = datetime.now()
            task.queue_position = None
            
            active_tasks[task_id] = asyncio.create_task(
                process_task(task_id)
            )
            
            active_tasks[task_id].add_done_callback(
                lambda t: active_tasks.pop(task_id, None)
            )
        
        await asyncio.sleep(1)

async def process_task(task_id: str):
    task = tasks[task_id]
    try:
        temp_dir = tempfile.mkdtemp()
        output_dir = os.path.join(temp_dir, 'stems')
        os.makedirs(output_dir, exist_ok=True)
        
        input_path = os.path.join(temp_dir, task.input_path)
        
        await separator.separate_audio(input_path, output_dir, task_id)
        task.completed_at = datetime.now()
        
    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        raise e

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(process_queue())

@app.post("/upload")
async def upload_audio(
    file: UploadFile = File(...)
):
    if not file.content_type or not file.content_type.startswith('audio/'):
        allowed_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg'}
        if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
            raise HTTPException(
                status_code=400, 
                detail="Invalid file type. Please upload an audio file."
            )
    
    task_id = str(uuid.uuid4())
    
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, file.filename)
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    tasks[task_id] = SeparationTask(
        task_id=task_id,
        status="queued",
        progress=0,
        input_path=input_path
    )
    
    task_queue.append(task_id)
    tasks[task_id].queue_position = len(task_queue)
    
    return {
        "task_id": task_id,
        "status": "queued",
        "queue_position": tasks[task_id].queue_position
    }

@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks[task_id]

@app.get("/download/{task_id}")
async def download_stems(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    
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

@app.get("/download/{task_id}/{stem_name}")
async def download_single_stem(task_id: str, stem_name: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    
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

@app.delete("/cleanup/{task_id}")
async def cleanup_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    
    if task.stems:
        for stem_path in task.stems:
            try:
                stem_dir = os.path.dirname(stem_path)
                if os.path.exists(stem_dir):
                    shutil.rmtree(os.path.dirname(stem_dir))
            except Exception as e:
                print(f"Error cleaning up {stem_path}: {e}")
    
    del tasks[task_id]
    
    return {"message": "Task cleaned up successfully"}

@app.get("/tasks")
async def list_tasks():
    return {"tasks": list(tasks.keys()), "count": len(tasks)}

@app.get("/queue/status")
async def get_queue_status():
    return {
        "queue_length": len(task_queue),
        "active_tasks": list(active_tasks.keys()),
        "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
        "queued_tasks": [
            {
                "task_id": task_id,
                "position": tasks[task_id].queue_position,
                "created_at": tasks[task_id].created_at
            }
            for task_id in task_queue
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)