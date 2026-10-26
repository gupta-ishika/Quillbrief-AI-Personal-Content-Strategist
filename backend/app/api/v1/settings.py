from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings as app_config
from app.db.repositories import (
    get_all_settings,
    get_or_create_creator,
    get_setting,
    set_setting,
)
from app.db.session import get_db
from app.scheduler import get_next_brief_time, sync_weekly_brief_job
from app.schemas.settings import SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/settings", tags=["settings"])


def _build_settings_response(db: Session) -> SettingsResponse:
    stored = get_all_settings(db)
    onboarding_completed = bool(stored.get("onboarding_completed", False))

    default_depth = stored.get("default_depth_level", app_config.default_depth_level)
    brief_day = stored.get("brief_day", app_config.default_brief_day)
    brief_time = stored.get("brief_time", app_config.default_brief_time)
    time_zone = stored.get("time_zone", app_config.default_time_zone)
    niche = stored.get("niche")
    tone_preset = stored.get("tone_preset")
    tone_instructions = stored.get("tone_instructions")

    next_brief = get_next_brief_time() if onboarding_completed else None

    return SettingsResponse(
        default_depth_level=default_depth,
        brief_day=brief_day,
        brief_time=brief_time,
        time_zone=time_zone,
        niche=niche,
        tone_preset=tone_preset,
        tone_instructions=tone_instructions,
        onboarding_completed=onboarding_completed,
        next_brief_at=next_brief,
    )


@router.get("", response_model=SettingsResponse)
def get_settings(db: Annotated[Session, Depends(get_db)]) -> SettingsResponse:
    return _build_settings_response(db)


@router.put("", response_model=SettingsResponse)
def update_settings(
    req: SettingsUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SettingsResponse:
    # First save ensures creator row exists (ADR-031, UT-36)
    get_or_create_creator(db)

    update_data = req.model_dump(exclude_unset=True)
    # Never allow updating onboarding_completed via PUT /settings
    update_data.pop("onboarding_completed", None)

    schedule_changed = any(k in update_data for k in ("brief_day", "brief_time", "time_zone"))

    for key, value in update_data.items():
        set_setting(db, key, value)

    onboarding_completed = bool(get_setting(db, "onboarding_completed") or False)
    if schedule_changed and onboarding_completed:
        sync_weekly_brief_job(db)

    return _build_settings_response(db)
