# Phase 1: Credential Vault Foundation
## Ubiquitous Language Glossary

| Term | Meaning |
|---|---|
| **Secret** | An encrypted privileged credential stored within the Vault. The primary Aggregate Root. |
| **Resource** | An existing Phase 0 managed asset (e.g., a server, database, or application) to which a Secret belongs. |
| **Vault** | The isolated bounded context responsible for the secure cryptographic lifecycle of Secrets. |
| **MEK** | Master Encryption Key. Managed externally, used to encrypt the DEK. |
| **DEK** | Data Encryption Key. Generated per Secret/Version, used to encrypt the payload. |
| **Policy** | The authorization decision mechanism that evaluates if an action is permitted. |
| **Domain Event** | An immutable business event published to the Event Bus (e.g., `SecretCreated`). |
| **Tombstone** | The logical deletion state of an entity. |
| **Correlation ID** | A unique identifier attached to operations and events to track requests across distributed boundaries (Audit, SIEM, Tracing). |
