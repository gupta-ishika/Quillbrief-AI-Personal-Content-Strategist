from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import Creator
from app.db.repositories import get_creator, set_setting
from app.db.session import get_db
from app.main import app
from app.scheduler import reset_scheduler


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    reset_scheduler()
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def do_connect(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        sess = session_factory()
        try:
            yield sess
        finally:
            sess.close()

    app.dependency_overrides[get_db] = override_get_db
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.clear()
        reset_scheduler()


@pytest.fixture
def api_client(db_session: Session) -> TestClient:
    return TestClient(app)


def test_get_settings_defaults(api_client: TestClient) -> None:
    res = api_client.get("/api/v1/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["default_depth_level"] == "standard"
    assert data["brief_day"] == "mon"
    assert data["brief_time"] == "08:00"
    assert data["time_zone"] == "Asia/Kolkata"
    assert data["niche"] is None
    assert data["tone_preset"] is None
    assert data["tone_instructions"] is None
    assert data["onboarding_completed"] is False
    assert data["next_brief_at"] is None


def test_put_settings_creates_creator_row(api_client: TestClient, db_session: Session) -> None:
    # Before PUT, no Creator row exists
    assert get_creator(db_session) is None

    res = api_client.put(
        "/api/v1/settings",
        json={"niche": "Tech and AI tutorials"},
    )
    assert res.status_code == 200
    assert res.json()["niche"] == "Tech and AI tutorials"

    # Creator row is created at first save (ADR-031, UT-36)
    creator = get_creator(db_session)
    assert creator is not None
    assert isinstance(creator, Creator)


def test_ut_34_niche_validation(api_client: TestClient) -> None:
    # 1. Empty niche rejected
    res_empty = api_client.put("/api/v1/settings", json={"niche": ""})
    assert res_empty.status_code == 422
    assert "niche" in str(res_empty.json())

    # 2. Whitespace-only niche rejected
    res_ws = api_client.put("/api/v1/settings", json={"niche": "   \t  "})
    assert res_ws.status_code == 422
    assert "niche" in str(res_ws.json())

    # 3. Niche over 200 chars rejected
    res_too_long = api_client.put("/api/v1/settings", json={"niche": "a" * 201})
    assert res_too_long.status_code == 422
    assert "niche" in str(res_too_long.json())

    # 4. Exactly 200 chars accepted
    res_200 = api_client.put("/api/v1/settings", json={"niche": "a" * 200})
    assert res_200.status_code == 200
    assert res_200.json()["niche"] == "a" * 200

    # 5. Control characters in niche rejected
    res_ctrl = api_client.put("/api/v1/settings", json={"niche": "Tech\x00Tutorials"})
    assert res_ctrl.status_code == 422
    assert "niche" in str(res_ctrl.json())

    res_nl = api_client.put("/api/v1/settings", json={"niche": "Tech\nTutorials"})
    assert res_nl.status_code == 422
    assert "niche" in str(res_nl.json())


def test_ut_34_tone_validation(api_client: TestClient) -> None:
    # 1. Unknown tone_preset rejected
    res_unknown = api_client.put("/api/v1/settings", json={"tone_preset": "sarcastic"})
    assert res_unknown.status_code == 422
    assert "tone_preset" in str(res_unknown.json())

    # 2. Valid tone_preset accepted
    for preset in ("professional", "friendly", "educational", "conversational", "humorous"):
        res_ok = api_client.put("/api/v1/settings", json={"tone_preset": preset})
        assert res_ok.status_code == 200
        assert res_ok.json()["tone_preset"] == preset

    # 3. Tone instructions over 500 chars rejected
    res_too_long = api_client.put("/api/v1/settings", json={"tone_instructions": "x" * 501})
    assert res_too_long.status_code == 422
    assert "tone_instructions" in str(res_too_long.json())

    # 4. Tone instructions exactly 500 chars accepted
    res_500 = api_client.put("/api/v1/settings", json={"tone_instructions": "x" * 500})
    assert res_500.status_code == 200
    assert res_500.json()["tone_instructions"] == "x" * 500

    # 5. Newlines in tone instructions accepted
    res_nl = api_client.put(
        "/api/v1/settings",
        json={"tone_instructions": "Line 1\nLine 2\r\nLine 3\tindented"},
    )
    assert res_nl.status_code == 200

    # 6. Non-whitespace control characters rejected
    res_ctrl = api_client.put(
        "/api/v1/settings",
        json={"tone_instructions": "Bad\x07sound"},
    )
    assert res_ctrl.status_code == 422
    assert "tone_instructions" in str(res_ctrl.json())


def test_ut_34_onboarding_completed_cannot_be_set_via_put_settings(
    api_client: TestClient,
) -> None:
    res = api_client.put("/api/v1/settings", json={"onboarding_completed": True})
    assert res.status_code == 422
    assert "onboarding_completed" in str(res.json())


def test_schedule_settings_validation_and_job_sync(
    api_client: TestClient, db_session: Session
) -> None:
    # 1. Invalid time zone rejected with 422
    res_bad_tz = api_client.put("/api/v1/settings", json={"time_zone": "Mars/Phobos"})
    assert res_bad_tz.status_code == 422
    assert "time_zone" in str(res_bad_tz.json())

    # 2. Valid time zone accepted
    res_ok_tz = api_client.put("/api/v1/settings", json={"time_zone": "America/New_York"})
    assert res_ok_tz.status_code == 200
    assert res_ok_tz.json()["time_zone"] == "America/New_York"
    # Schedule change before completion creates no job
    assert res_ok_tz.json()["next_brief_at"] is None

    # 3. When onboarding completed, schedule change updates next_brief_at
    set_setting(db_session, "onboarding_completed", True)
    res_sched = api_client.put(
        "/api/v1/settings",
        json={"brief_day": "tue", "brief_time": "10:30"},
    )
    assert res_sched.status_code == 200
    assert res_sched.json()["brief_day"] == "tue"
    assert res_sched.json()["brief_time"] == "10:30"
    assert res_sched.json()["next_brief_at"] is not None
