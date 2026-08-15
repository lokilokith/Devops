"""Expiration Worker – Phase 2D.

Automates cleanup of stale leases by invoking CheckoutService.process_expirations().
Reuses the WORKER_ACTOR_ID identity and CheckoutService's transaction boundaries.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from app.checkout.service import CheckoutService
from app.workers.rotation_worker import WORKER_ACTOR_ID

logger = logging.getLogger(__name__)

def run_expiration_job(
    session: Session,
    checkout_service: CheckoutService,
    actor_id: UUID | None = None,
) -> Dict[str, Any]:
    """Execute the background expiration sweep.

    Returns a dictionary of counts and duration.
    """
    if actor_id is None:
        actor_id = WORKER_ACTOR_ID

    run_id = str(uuid.uuid4())
    start_time = datetime.now(timezone.utc)

    logger.info("ExpirationWorker: starting - run_id=%s", run_id)

    try:
        attempted, succeeded = checkout_service.process_expirations()
        failed = attempted - succeeded
    except Exception as exc:
        logger.exception("ExpirationWorker: Catastrophic failure during process_expirations: %s", exc, extra={"run_id": run_id})
        raise

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    result = {
        "run_id": run_id,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "duration_seconds": round(duration, 3)
    }

    logger.info(
        "ExpirationWorker: completed - run_id=%s attempted=%d succeeded=%d failed=%d duration_seconds=%.3f",
        run_id, attempted, succeeded, failed, result["duration_seconds"],
        extra={"run_id": run_id}
    )

    return result
