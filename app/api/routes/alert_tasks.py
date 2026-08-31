# app/api/routes/alert_tasks.py

from celery.result import AsyncResult
from fastapi import APIRouter

from app.core.celery_app import celery_app
from app.schemas.alert_task import (
    AlertDispatchAccepted,
    AlertDispatchRequest,
    AlertTaskStatus,
)
from app.tasks.alerts import send_alert_email_task

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/dispatch", response_model=AlertDispatchAccepted, status_code=202)
def dispatch_alert(payload: AlertDispatchRequest) -> AlertDispatchAccepted:
    """Queue an alert email for background delivery and return its task id."""
    task = send_alert_email_task.delay(
        subject=payload.subject,
        body=payload.body,
        to=payload.to,
    )
    return AlertDispatchAccepted(task_id=task.id)


@router.get("/dispatch/{task_id}", response_model=AlertTaskStatus)
def get_alert_status(task_id: str) -> AlertTaskStatus:
    """Poll the status/result of a previously submitted alert task."""
    result = AsyncResult(task_id, app=celery_app)
    data = None
    if result.ready():
        data = result.result if isinstance(result.result, dict) else {"value": str(result.result)}
    return AlertTaskStatus(task_id=task_id, status=result.status, result=data)