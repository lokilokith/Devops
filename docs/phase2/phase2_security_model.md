# Phase 2 Security Model

## Threat Model

1. **Credential Theft**
   - *Threat*: Attackers compromise static privileged credentials.
   - *Mitigation*: JIT access and dynamic secrets ensure credentials are short-lived and useless outside the approval window.

2. **Privilege Escalation**
   - *Threat*: A user gains higher privileges than authorized.
   - *Mitigation*: The Policy Engine evaluates context (ABAC) in real-time, preventing access from unauthorized networks or outside business hours.

3. **Unauthorized Secret Access**
   - *Threat*: Malicious actor extracts secrets from the Vault.
   - *Mitigation*: Vault lifecycle manager automatically rotates secrets. Un-brokered direct access is disabled; all access goes through the Session Broker.

4. **Session Abuse**
   - *Threat*: An authorized user performs malicious actions during a valid session.
   - *Mitigation*: Session recording and real-time monitoring. Admins can actively terminate suspicious sessions.

5. **Approval Bypass**
   - *Threat*: Users bypass workflow to grant themselves access.
   - *Mitigation*: Cryptographic verification of approval chains and multi-tier quorum requirements.

## Security Controls
- **RBAC & ABAC**: Combined static roles with dynamic context policies.
- **Least Privilege**: Users have zero standing privileges (ZSP). Access is granted only when needed.
- **Temporary Access**: All elevated access has a hard expiry (JIT).
- **Audit Logging**: Immutable, tamper-evident logs for all access grants and session events.
- **Encryption**: Secrets encrypted at rest (Phase 1) with added automated key rotation (Phase 2).

## Access Lifecycle

```
Request (User asks for access to Server A)
  ↓
Policy Evaluation (Engine checks time, IP, risk level)
  ↓
Approval (Manager / Auto-approve based on rules)
  ↓
Temporary Privilege (JIT credentials generated or brokered)
  ↓
Session Monitoring (Broker records SSH/RDP session)
  ↓
Expiry/Revoke (Time limit reached, connection severed, credentials rotated)
  ↓
Audit (Full lifecycle logged to immutable storage)
```

## Security Assumptions and Limitations
- **Assumption**: The underlying infrastructure (OS, hypervisor) hosting OpsForge is secure and cannot be bypassed.
- **Assumption**: Target systems correctly integrate with the Session Management broker and reject direct connections.
- **Limitation**: Real-time anomaly detection relies on rules and may not catch novel attacks instantly.
- **Limitation**: Session recording for certain proprietary GUI protocols may be limited to video rather than indexed metadata.
