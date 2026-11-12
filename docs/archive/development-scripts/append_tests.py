tests = """
def test_revocation_engine_session_termination_failure(db_session, test_grant, mock_audit):
    repo = JITAccessRepository(db_session)
    executor = StubTargetExecutor(default_mode="target_failure")
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    with pytest.raises(JITAccessError, match="Session termination failed"):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=executor,
            worker_id="worker_1",
        )

def test_revocation_engine_revoke_jit_grant_uncertainty(db_session, test_grant, mock_audit):
    repo = JITAccessRepository(db_session)
    class CustomStubExecutor(StubTargetExecutor):
        def revoke_jit_grant(self, request):
            from app.execution.domain import ExecutionResult, ExecutionStatus, FailureClassification, ExecutionOperation, VerificationStatus
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.UNCERTAIN_STATE,
                error_message="Revoke uncertain"
            )
    custom_executor = CustomStubExecutor()
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    with pytest.raises(JITAccessError, match="Sudoers revocation failed"):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=custom_executor,
            worker_id="worker_1",
        )

def test_revocation_engine_revoke_jit_grant_failure(db_session, test_grant, mock_audit):
    repo = JITAccessRepository(db_session)
    class CustomStubExecutor(StubTargetExecutor):
        def revoke_jit_grant(self, request):
            from app.execution.domain import ExecutionResult, ExecutionStatus, FailureClassification, ExecutionOperation, VerificationStatus
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message="Revoke failed completely"
            )
    custom_executor = CustomStubExecutor()
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    with pytest.raises(JITAccessError, match="Revoke failed completely"):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=custom_executor,
            worker_id="worker_1",
        )
"""
with open("tests/jit_access/test_phase8_revocation_engine.py", "a") as f:
    f.write(tests)
