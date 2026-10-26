import asyncio
import logging
from collections.abc import Generator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db.repositories.settings import get_all_settings
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)

WEEKLY_BRIEF_JOB_ID = "weekly_brief"

DAY_NAME_MAP = {
    "mon": "mon",
    "monday": "mon",
    "0": "mon",
    "tue": "tue",
    "tuesday": "tue",
    "1": "tue",
    "wed": "wed",
    "wednesday": "wed",
    "2": "wed",
    "thu": "thu",
    "thursday": "thu",
    "3": "thu",
    "fri": "fri",
    "friday": "fri",
    "4": "fri",
    "sat": "sat",
    "saturday": "sat",
    "5": "sat",
    "sun": "sun",
    "sunday": "sun",
    "6": "sun",
}

_scheduler: AsyncIOScheduler | None = None


def placeholder_weekly_brief_job() -> None:
    """Target placeholder for Weekly Brief scheduled job.

    Does nothing until AGT-07 implements weekly brief generation (SCHED-00, ADR-022).
    """
    logger.info("Weekly brief placeholder job executed.")


def normalize_day_of_week(day_str: str | None) -> str:
    if not day_str:
        return "mon"
    clean = day_str.strip().lower()
    return DAY_NAME_MAP.get(clean, "mon")


def parse_time_string(time_str: str | None) -> tuple[int, int]:
    if not time_str:
        return 8, 0
    try:
        parts = time_str.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except Exception:
        logger.warning("Failed to parse time string '%s', defaulting to 08:00.", time_str)
    return 8, 0


def resolve_time_zone(tz_name: str | None) -> ZoneInfo:
    candidate = tz_name.strip() if tz_name else settings.default_time_zone
    try:
        return ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, Exception):
        logger.warning("Invalid time zone '%s', falling back to default.", tz_name)
    try:
        return ZoneInfo(settings.default_time_zone)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


def get_scheduler(custom_engine: Engine | None = None) -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        selected_engine = custom_engine or engine
        jobstore = SQLAlchemyJobStore(engine=selected_engine, tablename="apscheduler_jobs")
        _scheduler = AsyncIOScheduler(jobstores={"default": jobstore})
    return _scheduler


def start_scheduler(custom_engine: Engine | None = None) -> None:
    sched = get_scheduler(custom_engine)
    if not sched.running:
        if not sched._eventloop or sched._eventloop.is_closed():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            sched._eventloop = loop
        sched.start()
        logger.info("APScheduler started.")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        if _scheduler.running:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
        _scheduler = None
        logger.info("APScheduler stopped.")


def reset_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        if _scheduler.running:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
        _scheduler = None


def is_scheduler_running() -> bool:
    global _scheduler
    return bool(_scheduler is not None and _scheduler.running)


def get_next_brief_time() -> str | None:
    global _scheduler
    if _scheduler is None:
        return None
    job = _scheduler.get_job(WEEKLY_BRIEF_JOB_ID)
    if not job:
        return None

    next_run = getattr(job, "next_run_time", None)
    if next_run:
        return str(next_run.isoformat())

    # If job is pending and scheduler hasn't computed next_run_time yet
    if hasattr(job, "trigger") and job.trigger is not None:
        tz = getattr(job.trigger, "timezone", None)
        now = datetime.now(tz) if tz else datetime.now()
        next_fire = job.trigger.get_next_fire_time(None, now)
        if next_fire:
            return str(next_fire.isoformat())

    return None


def sync_weekly_brief_job(
    db: Session | None = None, custom_engine: Engine | None = None
) -> str | None:
    """Creates, removes, or replaces the Weekly Brief job from saved settings.

    Invariants (SCHED-00, ADR-022, ADR-031):
    1. Creates no job until onboarding_completed is true.
    2. Uses saved settings (brief_day, brief_time, time_zone) as source of truth.
    3. Replaces existing job immediately upon schedule update.
    """
    sched = get_scheduler(custom_engine)

    def _execute_sync(session: Session) -> str | None:
        app_settings: dict[str, Any] = get_all_settings(session)
        onboarding_completed = bool(app_settings.get("onboarding_completed", False))

        if not onboarding_completed:
            # Onboarding not completed - ensure no job exists
            remove_weekly_brief_job()
            return None

        # Onboarding is completed: extract schedule
        day_str = str(app_settings.get("brief_day", settings.default_brief_day))
        time_str = str(app_settings.get("brief_time", settings.default_brief_time))
        tz_str = str(app_settings.get("time_zone", settings.default_time_zone))

        day_of_week = normalize_day_of_week(day_str)
        hour, minute = parse_time_string(time_str)
        tz = resolve_time_zone(tz_str)

        trigger = CronTrigger(
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            timezone=tz,
        )

        sched.add_job(
            placeholder_weekly_brief_job,
            trigger=trigger,
            id=WEEKLY_BRIEF_JOB_ID,
            name="Weekly Brief",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        logger.info(
            "Scheduled weekly brief job: day=%s, hour=%d, minute=%d, tz=%s",
            day_of_week,
            hour,
            minute,
            tz,
        )
        return get_next_brief_time()

    if db is not None:
        return _execute_sync(db)

    def get_session() -> Generator[Session, None, None]:
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    session_gen = get_session()
    sess = next(session_gen)
    try:
        return _execute_sync(sess)
    finally:
        sess.close()


def remove_weekly_brief_job() -> bool:
    global _scheduler
    if _scheduler is None:
        return False
    try:
        _scheduler.remove_job(WEEKLY_BRIEF_JOB_ID)
        logger.info("Removed weekly brief scheduled job.")
        return True
    except (JobLookupError, KeyError):
        return False


def remove_all_jobs() -> int:
    """Removes all jobs from the scheduler (ADR-024 / DATABASE.md Section 11)."""
    global _scheduler
    if _scheduler is None:
        return 0
    jobs = _scheduler.get_jobs()
    count = len(jobs)
    _scheduler.remove_all_jobs()
    logger.info("Removed all (%d) scheduled jobs.", count)
    return count
