import uuid

from app.vault.executor_registry import ExecutorRegistry
from app.vault.executor_stub import StubCredentialExecutor


def test_registry_selects_capable_executor():
    resource_id = uuid.uuid4()
    stub = StubCredentialExecutor({resource_id: "success"})
    registry = ExecutorRegistry([stub])

    exe = registry.get_executor(resource_id)
    assert exe is not None
    assert exe.can_execute(resource_id)


def test_registry_returns_none_for_unsupported_resource():
    resource_supported = uuid.uuid4()
    resource_missing = uuid.uuid4()
    stub = StubCredentialExecutor({resource_supported: "success"})
    registry = ExecutorRegistry([stub])

    exe = registry.get_executor(resource_missing)
    assert exe is None
