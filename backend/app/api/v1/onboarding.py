from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.errors import AppException
from app.config import settings
from app.db.repositories import (
    clear_creator_channel,
    get_all_settings,
    get_creator,
    get_or_create_creator,
    get_setting,
    set_setting,
    update_creator_channel,
)
from app.db.session import get_db
from app.scheduler import get_next_brief_time, sync_weekly_brief_job
from app.schemas.onboarding import (
    ChannelResolveRequest,
    ChannelResolveResponse,
    ChannelResponse,
    ChannelUpdateRequest,
    CreatorChannelItem,
    OnboardingChannelValue,
    OnboardingCompleteResponse,
    OnboardingResponse,
    OnboardingStep,
    OnboardingValues,
)
from app.services.channel_resolver import parse_channel_identifier, resolve_channel

router = APIRouter(tags=["onboarding", "creator"])


@router.get("/onboarding", response_model=OnboardingResponse)
def get_onboarding_state(db: Annotated[Session, Depends(get_db)]) -> OnboardingResponse:
    stored = get_all_settings(db)
    onboarding_completed = bool(stored.get("onboarding_completed", False))
    channel_skipped = bool(stored.get("onboarding_channel_skipped", False))

    niche = stored.get("niche")
    tone_preset = stored.get("tone_preset")
    tone_instructions = stored.get("tone_instructions")

    creator = get_creator(db)
    has_channel = bool(creator and (creator.youtube_channel_id or creator.youtube_channel_handle))

    next_step: OnboardingStep
    if not niche:
        next_step = "niche"
    elif not tone_preset:
        next_step = "tone"
    elif not has_channel and not channel_skipped:
        next_step = "channel"
    else:
        next_step = "review"

    channel_val = None
    if creator and (creator.youtube_channel_id or creator.youtube_channel_handle):
        channel_val = OnboardingChannelValue(
            channel_id=creator.youtube_channel_id,
            handle=creator.youtube_channel_handle,
            title=creator.youtube_channel_title,
            verified=creator.youtube_channel_verified,
        )

    oauth_state = stored.get("youtube_oauth_state", "disconnected")

    return OnboardingResponse(
        onboarding_completed=onboarding_completed,
        next_step=next_step,
        values=OnboardingValues(
            niche=niche,
            tone_preset=tone_preset,
            tone_instructions=tone_instructions,
            channel=channel_val,
            api_key_configured=bool(settings.youtube_api_key),
            youtube_oauth={"state": oauth_state},
        ),
    )


@router.post("/onboarding/skip-channel")
def skip_channel(db: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    # Requires niche and tone saved (UT-36, API.md Section 7)
    niche = get_setting(db, "niche")
    tone_preset = get_setting(db, "tone_preset")
    if not niche or not tone_preset:
        missing = []
        if not niche:
            missing.append("niche")
        if not tone_preset:
            missing.append("tone_preset")
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="ONBOARDING_INCOMPLETE",
            message="Niche and tone must be saved before skipping channel step.",
            details={"missing": missing},
        )

    set_setting(db, "onboarding_channel_skipped", True)
    return {"onboarding_channel_skipped": True}


@router.post("/onboarding/complete", response_model=OnboardingCompleteResponse)
def complete_onboarding(
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingCompleteResponse:
    # Requires niche and tone_preset saved (UT-36, API.md Section 7)
    niche = get_setting(db, "niche")
    tone_preset = get_setting(db, "tone_preset")
    if not niche or not tone_preset:
        missing = []
        if not niche:
            missing.append("niche")
        if not tone_preset:
            missing.append("tone_preset")
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="ONBOARDING_INCOMPLETE",
            message="Niche and tone preset must be saved before completing onboarding.",
            details={"missing": missing},
        )

    # First save creates creators row if not exists
    get_or_create_creator(db)

    set_setting(db, "onboarding_completed", True)
    sync_weekly_brief_job(db)
    next_brief = get_next_brief_time()

    return OnboardingCompleteResponse(
        onboarding_completed=True,
        next_brief_at=next_brief,
    )


@router.post("/channel/resolve", response_model=ChannelResolveResponse)
async def resolve_channel_endpoint(
    req: ChannelResolveRequest,
) -> ChannelResolveResponse:
    res = await resolve_channel(req.identifier)
    return ChannelResolveResponse(**res)


@router.get("/creator/channels", response_model=list[CreatorChannelItem])
def list_connected_channels(
    db: Annotated[Session, Depends(get_db)],
) -> list[CreatorChannelItem]:
    oauth_state = get_setting(db, "youtube_oauth_state") or "disconnected"
    if oauth_state != "connected":
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="OAUTH_NOT_CONNECTED",
            message="YouTube account is not connected.",
        )
    return []


@router.put("/creator/channel", response_model=ChannelResponse)
async def update_channel(
    req: ChannelUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ChannelResponse:
    if req.identifier:
        id_type, id_value = parse_channel_identifier(req.identifier)

        if settings.youtube_api_key:
            res = await resolve_channel(req.identifier)
            if res.get("resolved"):
                channel_id = res.get("channel_id")
                title = res.get("title")
                handle = id_value if id_type == "handle" else None
                creator = update_creator_channel(
                    db,
                    channel_id=channel_id,
                    channel_handle=handle,
                    channel_title=title,
                    verified=True,
                )
                return ChannelResponse(
                    channel_id=creator.youtube_channel_id,
                    handle=creator.youtube_channel_handle,
                    title=creator.youtube_channel_title,
                    verified=creator.youtube_channel_verified,
                )

        # Without API key or unverified lookup: save parsed identifier as unverified (UT-35)
        channel_id = id_value if id_type == "channel_id" else None
        handle = id_value if id_type == "handle" else None
        creator = update_creator_channel(
            db,
            channel_id=channel_id,
            channel_handle=handle,
            channel_title=None,
            verified=False,
        )
        return ChannelResponse(
            channel_id=creator.youtube_channel_id,
            handle=creator.youtube_channel_handle,
            title=creator.youtube_channel_title,
            verified=creator.youtube_channel_verified,
        )

    if req.oauth_channel_id:
        oauth_state = get_setting(db, "youtube_oauth_state") or "disconnected"
        if oauth_state != "connected":
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                code="OAUTH_NOT_CONNECTED",
                message="YouTube account is not connected.",
            )
        # Check against connected channels list
        connected_channels: list[dict[str, str]] = get_setting(db, "connected_channels") or []
        matched = next(
            (c for c in connected_channels if c.get("channel_id") == req.oauth_channel_id),
            None,
        )
        if not matched:
            raise AppException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CHANNEL_NOT_FOUND",
                message=f"Channel ID '{req.oauth_channel_id}' is not in connected YouTube account.",
            )
        creator = update_creator_channel(
            db,
            channel_id=matched.get("channel_id"),
            channel_handle=matched.get("handle"),
            channel_title=matched.get("title"),
            verified=True,
        )
        return ChannelResponse(
            channel_id=creator.youtube_channel_id,
            handle=creator.youtube_channel_handle,
            title=creator.youtube_channel_title,
            verified=creator.youtube_channel_verified,
        )

    raise AppException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="INVALID_ARGUMENTS",
        message="Must provide identifier or oauth_channel_id.",
    )


@router.delete("/creator/channel", response_model=ChannelResponse)
def delete_channel(db: Annotated[Session, Depends(get_db)]) -> ChannelResponse:
    # ADR-032: Changing or removing the saved channel never deletes stored content
    creator = clear_creator_channel(db)
    return ChannelResponse(
        channel_id=creator.youtube_channel_id,
        handle=creator.youtube_channel_handle,
        title=creator.youtube_channel_title,
        verified=creator.youtube_channel_verified,
    )
