"""Repositories for Weekly Briefs, OAuth States, and Deletion Jobs (DB-05)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import DeletionJob, OAuthState, WeeklyBrief

# --- Weekly Briefs ---

def create_weekly_brief(
    db: Session,
    run_id: str,
    trigger: str,
    content_markdown: str,
    period_key: str | None = None,
    plan_id: str | None = None,
    status: str = "GENERATED",
) -> WeeklyBrief:
    """Creates a weekly brief.

    For scheduled briefs, period_key is required (e.g. '2026-W46').
    For manual briefs, period_key must be None.
    """
    brief = WeeklyBrief(
        run_id=run_id,
        trigger=trigger,
        period_key=period_key if trigger == "scheduled" else None,
        content_markdown=content_markdown,
        plan_id=plan_id,
        status=status,
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return brief


def get_weekly_brief(db: Session, brief_id: str) -> WeeklyBrief | None:
    return db.query(WeeklyBrief).filter_by(id=brief_id).first()


def get_weekly_brief_by_period_key(db: Session, period_key: str) -> WeeklyBrief | None:
    """Finds an existing scheduled weekly brief by period_key for duplicate protection (SCHED-02)."""
    return db.query(WeeklyBrief).filter_by(period_key=period_key, trigger="scheduled").first()


def get_latest_weekly_brief(db: Session) -> WeeklyBrief | None:
    return db.query(WeeklyBrief).order_by(WeeklyBrief.created_at.desc()).first()


def list_weekly_briefs(
    db: Session,
    status: str | None = None,
    limit: int = 50,
) -> list[WeeklyBrief]:
    query = db.query(WeeklyBrief)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(WeeklyBrief.created_at.desc()).limit(limit).all()


def mark_weekly_brief_read(db: Session, brief_id: str) -> WeeklyBrief | None:
    brief = get_weekly_brief(db, brief_id)
    if brief:
        brief.read_at = utc_now()
        db.commit()
        db.refresh(brief)
    return brief


def archive_weekly_brief(db: Session, brief_id: str) -> WeeklyBrief | None:
    brief = get_weekly_brief(db, brief_id)
    if brief:
        brief.status = "ARCHIVED"
        db.commit()
        db.refresh(brief)
    return brief


# --- OAuth States ---

def create_oauth_state(
    db: Session,
    state_hash: str,
    platform: str = "youtube",
    return_to: str = "settings",
    expires_in_minutes: int = 10,
) -> OAuthState:
    """Stores a short-lived (default 10 min) single-use OAuth state hash (CRED-03)."""
    now = utc_now()
    expires_at = now + timedelta(minutes=expires_in_minutes)
    oauth_state = OAuthState(
        state_hash=state_hash,
        platform=platform,
        return_to=return_to,
        expires_at=expires_at,
        created_at=now,
    )
    db.add(oauth_state)
    db.commit()
    db.refresh(oauth_state)
    return oauth_state


def get_oauth_state(db: Session, state_hash: str) -> OAuthState | None:
    return db.query(OAuthState).filter_by(state_hash=state_hash).first()


def mark_oauth_state_used(db: Session, state_hash: str) -> OAuthState | None:
    state = get_oauth_state(db, state_hash)
    if state:
        state.used_at = utc_now()
        db.commit()
        db.refresh(state)
    return state


def cleanup_expired_or_used_oauth_states(
    db: Session, now: datetime | None = None
) -> int:
    """Removes expired or used OAuth state records (RET-01)."""
    current_time = now or utc_now()
    ref_time = (
        current_time.astimezone(UTC).replace(tzinfo=None)
        if current_time.tzinfo is not None
        else current_time
    )

    all_states = db.query(OAuthState).all()
    count = 0
    for state in all_states:
        if state.used_at is not None:
            db.delete(state)
            count += 1
        elif state.expires_at is not None:
            exp_time = (
                state.expires_at.astimezone(UTC).replace(tzinfo=None)
                if state.expires_at.tzinfo is not None
                else state.expires_at
            )
            if exp_time <= ref_time:
                db.delete(state)
                count += 1
    if count > 0:
        db.commit()
    return count


# --- Deletion Jobs ---

def create_deletion_job(
    db: Session,
    steps_json: list[dict[str, Any]] | None = None,
) -> DeletionJob:
    """Creates a creator data deletion tracking job (DEL-01)."""
    job = DeletionJob(
        status="PENDING",
        steps_json=steps_json if steps_json is not None else [],
        requested_at=utc_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_deletion_job(db: Session, job_id: str) -> DeletionJob | None:
    return db.query(DeletionJob).filter_by(id=job_id).first()


def get_latest_deletion_job(db: Session) -> DeletionJob | None:
    return db.query(DeletionJob).order_by(DeletionJob.requested_at.desc()).first()


def update_deletion_job(
    db: Session,
    job_id: str,
    status: str,
    steps_json: list[dict[str, Any]] | None = None,
    finished_at: datetime | None = None,
) -> DeletionJob | None:
    job = get_deletion_job(db, job_id)
    if job:
        job.status = status
        if steps_json is not None:
            job.steps_json = steps_json
        if finished_at is not None:
            job.finished_at = finished_at
        elif status in ("COMPLETED", "FAILED", "PARTIAL"):
            job.finished_at = utc_now()
        db.commit()
        db.refresh(job)
    return job
