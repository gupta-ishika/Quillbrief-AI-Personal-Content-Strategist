"""Startup recovery service (ARCHITECTURE.md Section 12.1 and REC-01).

At backend startup, before accepting requests:
1. Runs in WAITING_APPROVAL are left alone. Their pending approvals and checkpoints are preserved.
2. Runs in RUNNING are set to INTERRUPTED and a recovery event is recorded.
   They are not resumed automatically, because the creator may not want a long model run to start unprompted.
3. The creator resumes an interrupted run (POST /runs/{id}/resume) or cancels it.
   Resume continues from the last checkpoint. Tasks marked DONE are not repeated.
4. Database writes made by tools are idempotent.
5. Pending approvals never become approved by recovery.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import Run
from app.db.repositories.runs import record_run_event


def recover_interrupted_runs(db: Session) -> list[str]:
    """Finds all runs stuck in RUNNING status and transitions them to INTERRUPTED.

    Records a 'recovery' event for each recovered run.
    Preserves WAITING_APPROVAL runs and pending approvals untouched.
    """
    running_runs = db.query(Run).filter(Run.status == "RUNNING").all()
    recovered_ids: list[str] = []

    for run in running_runs:
        run.status = "INTERRUPTED"
        run.updated_at = utc_now()
        recovery_payload: dict[str, Any] = {
            "message": "Run was active during backend restart and has been transitioned to INTERRUPTED.",
            "previous_status": "RUNNING",
            "recovered_at": utc_now().isoformat(),
        }
        record_run_event(
            db=db,
            run_id=run.id,
            event_type="recovery",
            payload=recovery_payload,
        )
        recovered_ids.append(run.id)

    if recovered_ids:
        db.commit()

    return recovered_ids
