import uuid

from pydantic import BaseModel


class LeadAssignRequest(BaseModel):
    assigned_user_id: uuid.UUID
    team_id: uuid.UUID
