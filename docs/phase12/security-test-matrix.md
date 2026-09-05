# Phase 12 Security Test Matrix

### Authorization attacks
* **wrong user**: Attempt to activate or use a session belonging to another user (IDOR).
* **wrong grant**: Attempt to bind a session to an unrelated grant.
* **wrong resource**: Attempt to use a session against a different resource.
* **wrong target account**: Attempt to elevate via a target account not bound to the grant.
* **wrong credential**: Attempt to inject an arbitrary credential ID.
* **expired authorization**: Attempt to activate a session after the grant has expired.
* **revoked authorization**: Attempt to activate a session after the grant has been revoked.
* **terminated session**: Attempt to connect to the broker using a token from a terminated session.
* **expired session**: Attempt to connect to the broker using a token from an expired session.

### Token attacks
* **malformed token**: Submit malformed/SQLi/XSS payloads as the session password token.
* **random token**: Submit randomly generated UUIDs/strings.
* **dead-session replay**: Replay a previously valid token after the session is explicitly terminated.
* **revoked-grant replay**: Replay a valid token after the underlying grant is revoked.
* **cross-grant replay**: Use token A to attempt access to grant B's target.
* **cross-resource replay**: Use token A to attempt access to resource B.
* **cross-target-account replay**: Use token A with target account B.

### Credential attacks
* **generic credential retrieval**: Verify no API allows direct `GET /credentials/{id}/decrypt`.
* **credential enumeration**: Attempt to enumerate credential IDs in the `CredentialUseService`.
* **secret in logs**: Verify broker and worker logs do not output `password` or `pkey` bytes.
* **secret in audit**: Verify audit events record "credential accessed" without the credential itself.
* **secret in API**: Verify no JSON responses contain the ephemeral SSH credential.
* **secret in frontend**: Verify React DevTools / local storage never possess the target credential.
* **secret in exceptions**: Induce `asyncssh` or Vault errors and ensure the traceback does not leak plaintext.

### Concurrency attacks
* **simultaneous activation (RACE-01)**: Two threads attempt to activate the same pending session simultaneously.
* **activation/revocation race (RACE-02)**: Thread A activates while Thread B revokes the grant. (OPEN - Genuine DB overlapping concurrency not proven)
* **activation/expiry race (RACE-03)**: Thread A activates at the exact millisecond the grant expires. (OPEN - Genuine DB overlapping concurrency not proven)
* **simultaneous revocation (RACE-04)**: Thread A and Thread B send terminate requests simultaneously.
* **duplicate session registration (RACE-05)**: Duplicate session registration should be rejected.
* **concurrent same token (RACE-06)**: Concurrent use of the same valid token after activation.
* **termination vs active operation (RACE-07)**: Active broker connection is dropped when revocation occurs.
* **worker retry after partial (RACE-08)**: Recover interrupted revocation safely.

### Session attacks
* **disconnect without revoke**: Close the SSH client socket abruptly and verify the session state remains correctly tracked until expiry.
* **reconnect after revoke**: Drop connection, revoke grant, attempt to reconnect with the same token. Must fail.
* **browser refresh**: Refresh the UI while a session is active. The UI must restore active state.
* **duplicate Connect**: Attempt to open multiple terminal tabs with the same session token.
* **stale UI**: UI shows "ACTIVE", but backend has expired the session. Attempting action must fail safely.
* **stale session token**: UI caches token, but session is dead.
* **session after worker restart**: Kill the worker process while a session is active. Verify reconciliation cleans it up.
