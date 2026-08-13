# API Contract Certification Evidence

| Endpoint | Method | Scenario | Expected | Actual | Result |
|---|---|---|---|---|---|
| `/auth/login` | POST | Valid login | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/auth/me` | GET | Fetch current user | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/users` | GET | List users | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/roles` | GET | List roles | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/roles/{id}` | GET | Get single role | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/permissions` | GET | List permissions | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/resources` | GET | List resources | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/vault/secrets` | GET | List secrets | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/vault/secrets` | GET | No sensitive leak in listing | No payload/ciphertext | No payload/ciphertext | **PASS** |
| `/vault/secrets/stats` | GET | Get vault stats | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/access-requests` | GET | List access requests | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/approval-workflows` | GET | List approval workflows | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/notifications` | GET | List notifications | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/notifications/unread-count` | GET | Unread count | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/audit` | GET | List audit logs | Status 200 + Valid Schema | Status 200 + Valid Schema | **PASS** |
| `/vault/secrets/{id}` | GET | Get non-existent secret (method not allowed) | Status 405 | Status 405 | **PASS** |
| `/vault/secrets` | GET | Missing Auth Token | Status 401 | Status 401 | **PASS** |
| `/vault/secrets` | POST | Validation Error (Empty Name) | Status 400 | Status 400 | **PASS** |
