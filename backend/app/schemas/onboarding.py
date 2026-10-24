from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

OnboardingStep = Literal["niche", "tone", "channel", "review"]


class OnboardingChannelValue(BaseModel):
    channel_id: str | None = None
    handle: str | None = None
    title: str | None = None
    verified: bool = False


class OnboardingValues(BaseModel):
    niche: str | None = None
    tone_preset: str | None = None
    tone_instructions: str | None = None
    channel: OnboardingChannelValue | None = None
    api_key_configured: bool = False
    youtube_oauth: dict[str, str] = Field(default_factory=lambda: {"state": "disconnected"})


class OnboardingResponse(BaseModel):
    onboarding_completed: bool
    next_step: OnboardingStep
    values: OnboardingValues


class OnboardingCompleteResponse(BaseModel):
    onboarding_completed: bool
    next_brief_at: str | None = None


class ChannelResolveRequest(BaseModel):
    identifier: str = Field(
        ...,
        min_length=1,
        description="Handle (@name), channel ID (UC...), or supported channel URL",
    )


class ChannelResolveParsed(BaseModel):
    type: Literal["handle", "channel_id"]
    value: str


class ChannelResolveResponse(BaseModel):
    resolved: bool
    channel_id: str | None = None
    title: str | None = None
    reason: str | None = None
    parsed: ChannelResolveParsed | None = None


class CreatorChannelItem(BaseModel):
    channel_id: str
    title: str
    custom_url: str | None = None
    thumbnail_url: str | None = None


class ChannelUpdateRequest(BaseModel):
    identifier: str | None = None
    oauth_channel_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def check_exactly_one_field(cls, data: Any) -> Any:
        if isinstance(data, dict):
            id_val = data.get("identifier")
            oauth_val = data.get("oauth_channel_id")
            if (id_val is None and oauth_val is None) or (
                id_val is not None and oauth_val is not None
            ):
                raise ValueError("Must provide exactly one of identifier or oauth_channel_id.")
        return data


class ChannelResponse(BaseModel):
    channel_id: str | None = None
    handle: str | None = None
    title: str | None = None
    verified: bool = False
