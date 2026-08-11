# Phase 2 Test Strategy

## Unit Testing
- **Services**: Test JIT provisioning logic, ensuring time bounds are strictly enforced. Unit test the `Policy Engine` to verify it correctly evaluates combinations of IP restrictions, time boundaries, and roles.
- **Policies**: Unit test creation, updating, and serialization of complex ABAC JSON conditions.
- **Sessions**: Mock the session broker to test start, pause, and termination signaling within the application logic.

## Integration Testing
- **API Workflows**:
  - Request -> Auto-approve (based on policy) -> Start Session -> Terminate Session.
  - Request -> Manual Approve -> Start Session -> Expiry (simulate time pass) -> Verify Session is killed.
- **Vault Rotation**: Test integration between the `Vault Lifecycle Manager` and dummy target databases to ensure credentials rotate at correct intervals.

## Security Testing
- **Privilege Escalation**: Attempt to access `/api/v1/sessions/start` with a standard token lacking a JIT approval. Ensure 403 Forbidden.
- **Unauthorized Access**: Attempt to bypass the broker and connect to a mock target directly; target must reject based on firewall rules.
- **Expired Access**: Simulate session continuation after JIT expiration. The session must be forcefully dropped by the broker.

## Performance Testing
- **Concurrent Requests**: Benchmark the `Approval Workflow` under high load to ensure lock contention does not slow down JIT grants.
- **Session Creation**: Measure latency from `POST /sessions/start` to broker readiness (must be < 2 seconds).
- **Policy Evaluation**: Benchmark the ABAC `Policy Engine` when evaluating hundreds of rules per request.

## Evidence Requirements
- **Logs**: Provide sample logs demonstrating a full JIT lifecycle (Request -> Approve -> Session -> Expire).
- **Screenshots**: Provide visual proof of the new Phase 2 UI (Session monitoring dashboard, Policy editor).
- **SQL Validation**: Show database row state transitions in `privileged_access_sessions` and `session_events`.
- **Reports**: Generate automated HTML coverage and compliance reports proving requirements are met.
