# Database Integrity Evidence

| Check | Expected | Actual | Result |
|---|---|---|---|
| vault_secrets.current_version_id FK | 0 orphans | 0 orphans | **PASS** |
| vault_secret_versions.vault_secret_id FK | 0 orphans | 0 orphans | **PASS** |
| Active Secret current version | 0 missing | 0 missing | **PASS** |
| Encrypted Payload existence | 0 empty | 0 empty | **PASS** |
| Audit Required Fields | 0 invalid | 0 invalid | **PASS** |
| Audit Enum Constraints | 0 invalid | 0 invalid | **PASS** |
| access_requests.requester_id FK | 0 invalid | 0 invalid | **PASS** |
| approval_workflows.access_request_id FK | 0 invalid | 0 invalid | **PASS** |
