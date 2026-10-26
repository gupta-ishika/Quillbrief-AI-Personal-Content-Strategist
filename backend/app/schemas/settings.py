from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TonePreset = Literal[
    "professional",
    "friendly",
    "educational",
    "conversational",
    "humorous",
]

DeletionJobStatus = Literal["PENDING", "RUNNING", "COMPLETED", "PARTIAL", "FAILED"]
DeletionStepStatus = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED"]


class SettingsResponse(BaseModel):
    default_depth_level: str
    brief_day: str
    brief_time: str
    time_zone: str
    niche: str | None = None
    tone_preset: TonePreset | None = None
    tone_instructions: str | None = None
    onboarding_completed: bool
    next_brief_at: str | None = None


class SettingsUpdateRequest(BaseModel):
    default_depth_level: Literal["quick", "standard", "deep"] | None = None
    brief_day: str | None = None
    brief_time: str | None = None
    time_zone: str | None = None
    niche: str | None = None
    tone_preset: TonePreset | None = None
    tone_instructions: str | None = None

    onboarding_completed: Any = None

    @field_validator("onboarding_completed")
    @classmethod
    def validate_onboarding_completed(cls, v: Any) -> None:
        if v is not None:
            raise ValueError("onboarding_completed cannot be set through settings.")

    @field_validator("niche")
    @classmethod
    def validate_niche(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Niche cannot be empty or whitespace only.")
        if len(v) > 200:
            raise ValueError("Niche must be 200 characters or fewer.")
        # Reject control characters
        if any(ord(c) < 32 for c in v):
            raise ValueError("Niche contains forbidden control characters.")
        return v

    @field_validator("tone_instructions")
    @classmethod
    def validate_tone_instructions(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) > 500:
            raise ValueError("Tone instructions must be 500 characters or fewer.")
        # Reject control characters except newlines and tabs
        if any(ord(c) < 32 and c not in ("\n", "\r", "\t") for c in v):
            raise ValueError("Tone instructions contain forbidden control characters.")
        return v

    @field_validator("time_zone")
    @classmethod
    def validate_time_zone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(v)
        except Exception as err:
            raise ValueError(f"Invalid IANA time zone: '{v}'.") from err
        return v

    @field_validator("brief_day")
    @classmethod
    def validate_brief_day(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        allowed = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        if v not in allowed:
            raise ValueError(f"brief_day must be one of {allowed}.")
        return v

    @field_validator("brief_time")
    @classmethod
    def validate_brief_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        import re

        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("brief_time must be in HH:MM format (00:00 to 23:59).")
        return v


class OAuthStartRequest(BaseModel):
    return_to: Literal["settings", "onboarding"] = Field(
        default="settings", description="Fixed return destination after OAuth callback"
    )


class OAuthStartResponse(BaseModel):
    authorization_url: str


class CredentialItemStatus(BaseModel):
    configured: bool | None = None
    state: Literal["connected", "needs_reauth", "disconnected"] | None = None


class CredentialsStatusResponse(BaseModel):
    api_key: dict[str, bool]
    youtube_oauth: dict[str, str]
    instagram: dict[str, str]


class DataDeletionRequest(BaseModel):
    confirm_text: str = Field(..., description="Must equal 'DELETE MY DATA'")

    @field_validator("confirm_text")
    @classmethod
    def validate_confirmation(cls, v: str) -> str:
        if v != "DELETE MY DATA":
            raise ValueError("Confirmation text must exactly equal 'DELETE MY DATA'.")
        return v


class DataDeletionResponse(BaseModel):
    deletion_job_id: str


class DeletionStepDetail(BaseModel):
    step: str
    status: DeletionStepStatus
    error: str | None = None


class DeletionJobResponse(BaseModel):
    id: str
    status: DeletionJobStatus
    steps: list[DeletionStepDetail] = Field(default_factory=list)
    requested_at: datetime
    finished_at: datetime | None = None
