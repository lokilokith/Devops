# Performance Certification Evidence

Test load: 50 requests concurrently per endpoint.

| Endpoint | Expected P95 | Actual P95 | Result |
|---|---|---|---|
| http://localhost/api/v1/vault/secrets | < 500ms | 160.73ms (Mean: 32.94ms) | **PASS** |
| http://localhost/api/v1/audit | < 500ms | 123.73ms (Mean: 27.53ms) | **PASS** |
