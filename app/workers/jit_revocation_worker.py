"""JIT Revocation Worker – Phase 8.

Autonomous worker for revocation processing, worker lease fencing, and crash recovery.
"""

from __future__ import annotations

from app.workers.jit_expiry_worker import (
    JITExpiryWorker,
    run_jit_expiry_job,
)

# Canonical Phase 8 aliases
JITRevocationWorker = JITExpiryWorker
run_jit_revocation_job = run_jit_expiry_job

__all__ = [
    "JITRevocationWorker",
    "run_jit_revocation_job",
    "JITExpiryWorker",
    "run_jit_expiry_job",
]
