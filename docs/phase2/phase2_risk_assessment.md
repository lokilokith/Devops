# Phase 2 Compatibility & Risk Assessment

## Compatibility Review

### Does Phase 2 break Vault?
**No.** The Vault architecture from Phase 1 remains intact. Phase 2 introduces `secret_rotation_policies`, which sits alongside existing `vault_items`. Static secrets will continue to work exactly as they did in Phase 1 unless explicitly assigned a rotation policy.

### Does Phase 2 break RBAC?
**No.** Phase 1 RBAC is the foundation. Phase 2 (ABAC and JIT) acts as an overlay. If a user has static access from Phase 1, it will be respected unless the administrator migrates them to a JIT policy. The `user_roles` and `role_permissions` schema remains unchanged.

### Does Phase 2 break Audit?
**No, it enhances it.** Existing audit logs remain. Phase 2 introduces a dedicated `session_events` table for high-volume session data to prevent bloating the Phase 1 main `audit_logs` table. This separation of concerns ensures backwards compatibility.

### Does Phase 2 require migration risks?
**Low Risk.** The database migrations for Phase 2 are strictly additive. No existing columns are altered or dropped. The risk lies entirely in potential bugs within the new `Policy Engine` incorrectly denying Phase 1 access, which will be mitigated by a phased rollout and "shadow mode" policy testing.

## Known Risks and Mitigations

1. **Broker Latency Risk**
   - *Risk*: The new Session Management Broker could introduce unacceptable latency for SSH/RDP connections.
   - *Mitigation*: Perform early benchmarking (as defined in the Test Plan) and use optimized proxy libraries.

2. **Rotation Outage Risk**
   - *Risk*: Automated secret rotation fails, locking OpsForge out of the target system while users also lose access.
   - *Mitigation*: Implement a rollback mechanism in rotation scripts and retain the `n-1` password until the new password is confirmed working.

3. **Database Growth**
   - *Risk*: Keystroke logging and session events will rapidly expand database size.
   - *Mitigation*: Implement data retention policies and archive older `session_events` to cold storage after 30 days.
