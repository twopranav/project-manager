from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.user import User, GlobalRole
from app.models.security_alert import SecurityAlert
from app.schemas.security_alert import SecurityAlertOut
from app.api.deps import get_current_user
from sqlalchemy.exc import IntegrityError
from app.schemas.user import UserOut, TransferAdminRequest
from app.core.security_alerts import log_unauthorized_role_change

# Create the router that exposes all admin endpoints under the /admin URL prefix.
router = APIRouter(prefix="/admin", tags=["admin"])

# Define a reusable authorization check that allows only the site-wide administrator to continue.
def _require_site_admin(current_user: User) -> None:
# Reject the request when the authenticated user does not have the site-admin role.
    if current_user.global_role != GlobalRole.admin:
# Return HTTP 403 because security-alert access is restricted to the site admin.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the site admin can view security alerts",
        )

@router.get("/alerts", response_model=List[SecurityAlertOut])
# Handle the security-alert listing request using the database and authenticated user supplied by FastAPI.
def list_security_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_resolved: bool = Query(default=False),
):
# Enforce the site-admin permission before reading any security alerts.
    _require_site_admin(current_user)
# Start a database query for all security-alert records.
    query = db.query(SecurityAlert)
# By default, restrict the query to alerts that have not yet been resolved.
    if not include_resolved:
# Add a filter that excludes resolved alerts from the result set.
        query = query.filter(SecurityAlert.resolved == False)
# Sort newest alerts first and return the complete result list.
    return query.order_by(SecurityAlert.created_at.desc()).all()

@router.patch("/alerts/{alert_id}/resolve", response_model=SecurityAlertOut)
# Handle the request to resolve a specific security alert.
def resolve_security_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
# Enforce the site-admin permission before reading any security alerts.
    _require_site_admin(current_user)
# Look up the requested security alert by its identifier.
    alert = db.query(SecurityAlert).filter(SecurityAlert.id == alert_id).first()
# Check whether the requested alert exists before modifying it, handle error with HTTP 404
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

# Mark the alert as resolved.
    alert.resolved = True
# Persist the resolution change to the database.
    db.commit()
# Reload the alert so the returned object reflects the committed database state.
    db.refresh(alert)
# Return the updated security alert to the caller.
    return alert

# Endpoint for transferring global admin rights to another user.
@router.post("/transfer-admin", response_model=UserOut)
def transfer_admin(
    payload: TransferAdminRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.global_role != GlobalRole.admin:
        log_unauthorized_role_change(
            db=db,
            actor=current_user,
            target_user_id=payload.new_admin_user_id,
            attempted_role="admin (via transfer)",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the site admin can transfer admin")

    target = db.query(User).filter(User.id == payload.new_admin_user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already the admin")

    try:
        current_user.global_role = GlobalRole.member
        db.flush()          # <-- THIS IS THE NEW LINE
        target.global_role = GlobalRole.admin
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin transfer failed — try again")

    db.refresh(target)
    return target