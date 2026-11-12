import uuid

import pytest

from app.vault.executor_stub import StubCredentialExecutor


def test_success_execution_returns_opaque_bytes():
    resource_id = uuid.uuid4()
    stub = StubCredentialExecutor({resource_id: "success"})
    result = stub.execute(resource_id, b"old_secret")
    # Ensure returned value is opaque bytes and not the input.
    assert isinstance(result["new_secret_version"], bytes)
    assert result["new_secret_version"] != b"old_secret"
    assert result["metadata"]["generated_by"] == "stub"
    assert result.get("error", "") == ""


def test_retry_mode_raises_generic_error():
    resource_id = uuid.uuid4()
    stub = StubCredentialExecutor({resource_id: "retry"})
    with pytest.raises(RuntimeError) as exc:
        stub.execute(resource_id, b"old_secret")
    # Message must contain the word 'retryable' (case‑insensitive) and not the secret.
    msg = str(exc.value).lower()
    assert "retryable" in msg
    assert "old_secret" not in msg


def test_terminal_mode_raises_generic_error():
    resource_id = uuid.uuid4()
    stub = StubCredentialExecutor({resource_id: "terminal"})
    with pytest.raises(RuntimeError) as exc:
        stub.execute(resource_id, b"old_secret")
    msg = str(exc.value).lower()
    assert "terminal" in msg
    assert "old_secret" not in msg


def test_can_execute_returns_false_for_unknown_resource():
    known_id = uuid.uuid4()
    unknown_id = uuid.uuid4()
    stub = StubCredentialExecutor({known_id: "success"})
    assert stub.can_execute(known_id) is True
    assert stub.can_execute(unknown_id) is False
