import asyncio
from collections import deque
from datetime import datetime
from typing import Dict
from app.models.task import SeparationTask

class TaskManager:
    def __init__(self, max_concurrent_tasks: int = 2):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.task_queue = deque()
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.tasks: Dict[str, SeparationTask] = {}

    async def process_queue(self, process_task_func):
        while True:
            if len(self.active_tasks) < self.max_concurrent_tasks and self.task_queue:
                task_id = self.task_queue.popleft()
                task = self.tasks[task_id]
                task.status = "processing"
                task.started_at = datetime.now()
                task.queue_position = None
                
                # Create background task for processing
                self.active_tasks[task_id] = asyncio.create_task(
                    process_task_func(task_id)
                )
                
                # Add callback to remove from active tasks when done
                self.active_tasks[task_id].add_done_callback(
                    lambda t: self.active_tasks.pop(task_id, None)
                )
            
            await asyncio.sleep(1)  # Check queue every second

    def add_task(self, task_id: str, input_path: str) -> SeparationTask:
        task = SeparationTask(
            task_id=task_id,
            status="queued",
            progress=0,
            input_path=input_path
        )
        
        self.tasks[task_id] = task
        self.task_queue.append(task_id)
        task.queue_position = len(self.task_queue)
        
        return task

    def get_task(self, task_id: str) -> SeparationTask:
        return self.tasks.get(task_id)

    def get_queue_status(self):
        return {
            "queue_length": len(self.task_queue),
            "active_tasks": len(self.active_tasks),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "queued_tasks": [
                {
                    "task_id": task_id,
                    "position": self.tasks[task_id].queue_position,
                    "created_at": self.tasks[task_id].created_at
                }
                for task_id in self.task_queue
            ],
            "active_task_ids": list(self.active_tasks.keys())
        }

    def list_tasks(self):
        return {"tasks": list(self.tasks.keys()), "count": len(self.tasks)}

    def cleanup_task(self, task_id: str):
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False 