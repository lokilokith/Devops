"""JIT Access Domain Events."""

from __future__ import annotations

from blinker import Namespace

jit_signals = Namespace()

jit_session_created = jit_signals.signal("jit_session_created")
jit_session_expired = jit_signals.signal("jit_session_expired")
jit_session_revoked = jit_signals.signal("jit_session_revoked")
