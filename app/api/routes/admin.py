from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.user import User, GlobalRole
from app.models.security_alert import SecurityAlert
from app.schemas.security_alert import SecurityAlertOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_site_admin(current_user: User) -> None:
    if current_user.global_role != GlobalRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the site admin can view security alerts",
        )


@router.get("/alerts", response_model=List[SecurityAlertOut])
def list_security_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_resolved: bool = Query(default=False),
):
    _require_site_admin(current_user)

    query = db.query(SecurityAlert)
    if not include_resolved:
        query = query.filter(SecurityAlert.resolved == False)

    return query.order_by(SecurityAlert.created_at.desc()).all()


@router.patch("/alerts/{alert_id}/resolve", response_model=SecurityAlertOut)
def resolve_security_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_site_admin(current_user)

    alert = db.query(SecurityAlert).filter(SecurityAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    alert.resolved = True
    db.commit()
    db.refresh(alert)
    return alert