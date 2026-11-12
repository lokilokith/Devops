tests = """
def test_revocation_engine_session_termination_failure(db_session, test_grant, mock_audit):
    repo = JITAccessRepository(db_session)
    class CustomStubExecutor(StubTargetExecutor):
        def terminate_jit_sessions(self, request):
            from app.execution.domain import ExecutionResult, ExecutionStatus, FailureClassification, ExecutionOperation, VerificationStatus
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.UNVERIFIED,
                failure_classification=FailureClassification.TARGET_FAILURE,
                error_message="Term failed completely"
            )
    executor = CustomStubExecutor()
    engine = JITRevocationEngine(repository=repo, audit_service=mock_audit)

    with pytest.raises(JITAccessError, match="Failed to terminate JIT sessions: Term failed completely"):
        engine.revoke_grant(
            grant_id=test_grant.id,
            actor_id=test_grant.user_id,
            executor=executor,
            worker_id="worker_1",
        )
"""
with open("tests/jit_access/test_phase8_revocation_engine.py", "a") as f:
    f.write(tests)
