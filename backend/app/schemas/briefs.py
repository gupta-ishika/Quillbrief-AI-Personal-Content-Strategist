from datetime import datetime
from typing import Literal

from pydantic import BaseModel

BriefTrigger = Literal["scheduled", "manual"]
BriefStatus = Literal["GENERATED", "ARCHIVED"]


class WeeklyBriefResponse(BaseModel):
    id: str
    run_id: str
    trigger: BriefTrigger
    period_key: str | None = None
    content_markdown: str
    plan_id: str | None = None
    status: BriefStatus
    read_at: datetime | None = None
    created_at: datetime


class WeeklyBriefRunResponse(BaseModel):
    run_id: str
