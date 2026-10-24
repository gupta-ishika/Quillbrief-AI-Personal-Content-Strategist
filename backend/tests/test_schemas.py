import pytest
from pydantic import ValidationError

from app.schemas import (
    ChannelUpdateRequest,
    DataDeletionRequest,
    PlanEditItem,
    PlanEditRequest,
    RunCreateRequest,
    SettingsUpdateRequest,
)


def test_settings_niche_validation() -> None:
    # Valid niche
    req = SettingsUpdateRequest(niche="  Python Tutorials and FastAPI  ")
    assert req.niche == "Python Tutorials and FastAPI"

    # Empty niche rejected
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(niche="   ")

    # Over 200 chars rejected
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(niche="a" * 201)

    # Exactly 200 chars accepted
    req200 = SettingsUpdateRequest(niche="a" * 200)
    assert req200.niche == "a" * 200

    # Control chars rejected
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(niche="Python\x00Tutorials")


def test_settings_tone_validation() -> None:
    # Valid presets
    for preset in ("professional", "friendly", "educational", "conversational", "humorous"):
        req = SettingsUpdateRequest(tone_preset=preset)  # type: ignore[arg-type]
        assert req.tone_preset == preset

    # Invalid preset rejected
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(tone_preset="sarcastic")  # type: ignore[arg-type]

    # Tone instructions up to 500 chars accepted, newlines allowed
    req_instr = SettingsUpdateRequest(
        tone_instructions="Friendly.\nPractical examples.\tClear explanations."
    )
    assert req_instr.tone_instructions is not None

    # Over 500 chars rejected
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(tone_instructions="a" * 501)


def test_data_deletion_confirmation() -> None:
    # Exact phrase matches
    req = DataDeletionRequest(confirm_text="DELETE MY DATA")
    assert req.confirm_text == "DELETE MY DATA"

    # Mismatch rejected
    with pytest.raises(ValidationError):
        DataDeletionRequest(confirm_text="delete my data")

    with pytest.raises(ValidationError):
        DataDeletionRequest(confirm_text="DELETE")


def test_channel_update_exactly_one_field() -> None:
    # Providing identifier only is valid
    req1 = ChannelUpdateRequest(identifier="@myhandle")
    assert req1.identifier == "@myhandle"

    # Providing oauth_channel_id only is valid
    req2 = ChannelUpdateRequest(oauth_channel_id="UC1234567890123456789012")
    assert req2.oauth_channel_id == "UC1234567890123456789012"

    # Providing neither is invalid
    with pytest.raises(ValidationError):
        ChannelUpdateRequest()

    # Providing both is invalid
    with pytest.raises(ValidationError):
        ChannelUpdateRequest(identifier="@myhandle", oauth_channel_id="UC1234567890123456789012")


def test_run_create_validation() -> None:
    req = RunCreateRequest(goal_text="Grow audience with tutorials", depth_level="quick")
    assert req.depth_level == "quick"

    with pytest.raises(ValidationError):
        RunCreateRequest(goal_text="")


def test_plan_edit_validation() -> None:
    req = PlanEditRequest(
        items=[
            PlanEditItem(
                topic="FastAPI Dependency Injection",
                format="long_form",
                platform="youtube",
                objective="Teach DI",
                reason="Audience question",
                source_type="comment",
            )
        ],
        expected_version=1,
    )
    assert len(req.items) == 1
    assert req.expected_version == 1
