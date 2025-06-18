from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

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