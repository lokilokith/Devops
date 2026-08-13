# Dashboard Integrity Evidence

| Metric | Expected | Actual | Result |
|---|---|---|---|
| Dashboard API Availability | HTTP 200 | HTTP 200 | **PASS** |
| Access Requests Aggregation | pending/approved keys exist | Keys: ['pending', 'approved'] | **PASS** |
| Active Secrets Aggregation | Integer active_secrets exists | int | **PASS** |
| Unread Notifications Aggregation | Integer unread_notifications exists | int | **PASS** |
