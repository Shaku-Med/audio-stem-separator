import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router, task_manager, process_task

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

app.include_router(router)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(task_manager.process_queue(process_task))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 