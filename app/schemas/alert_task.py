from typing import Optional
from pydantic import BaseModel


class AlertDispatchRequest(BaseModel):
    subject: str
    body: str
    to: Optional[str] = None


class AlertDispatchAccepted(BaseModel):
    task_id: str


class AlertTaskStatus(BaseModel):
    task_id: str
    status: str  # celery states: PENDING, STARTED, SUCCESS, FAILURE, RETRY
    result: Optional[dict] = None