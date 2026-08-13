# Security Negative Certification Evidence

| Test Category | Attack/Scenario | Expected | Actual | Result |
|---|---|---|---|---|
| JWT | Missing token | Status 401 | Status 401 | **PASS** |
| JWT | Malformed token | Status 401/422 | Status 401 | **PASS** |
| JWT | Invalid signature | Status 401/422 | Status 401 | **PASS** |
| Input Validation | Invalid UUID format in URL | Status 404/400/405/422 | Status 422 | **PASS** |
| Input Validation | Missing required fields (POST /users) | Status 400/422 | Status 422 | **PASS** |
| Input Validation | Malformed JSON payload | Status 400 | Status 400 | **PASS** |
| Input Validation | Invalid Enum value (RoleStatus) | Status 400/422 | Status 422 | **PASS** |
| Injection | SQL injection string in search query | Status 200 (Safe) | Status 200 | **PASS** |
| Injection | XSS string in resource name | Status != 500 | Status 422 | **PASS** |
| Resource State | Retrieve active secret without access request | Status 403 | Status 403 | **PASS** |
| Resource State | Disable secret | Status 200 | Status 200 | **PASS** |
| Resource State | Retrieve disabled secret | Status 400/403/409 | Status 400 | **PASS** |
| Resource State | Rotate disabled secret | Status 400/409 | Status 400 | **PASS** |
| Sensitive Data | Plaintext not in DB | Encrypted payload | Encrypted | **PASS** |
| Sensitive Data | Plaintext not in Audit logs | Clean audit logs | Clean | **PASS** |
