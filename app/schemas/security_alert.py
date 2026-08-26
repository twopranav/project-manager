from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# Output schema describing a security alert, including actor, optional target, timestamp, and resolution state.
class SecurityAlertOut(BaseModel):
    id: str
    alert_type: str
    message: str
    actor_user_id: str
    target_user_id: Optional[str]
    target_id: Optional[str]
    created_at: datetime
    resolved: bool
    # Allow Pydantic to populate this output schema directly from ORM model attributes.
    class Config:
        from_attributes = True  