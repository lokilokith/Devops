# Phase 1: Credential Vault Foundation
## Encryption Design

### 1. Overview
This document defines the cryptographic architecture and key management lifecycle for the Vault Domain. It specifies the Envelope Encryption strategy, cryptographic primitives, and the abstraction layer for Key Management Systems (KMS).

### 2. Key Hierarchy (Envelope Encryption)
The system utilizes a two-tier key hierarchy to isolate and protect cryptographic material.

- **Master Encryption Key (MEK)**
  - Managed exclusively by an external Key Provider (e.g., AWS KMS, HashiCorp Vault, or injected via secure environment variables in Phase 1).
  - The MEK never resides in persistent database storage.
  - Purpose: Encrypts and decrypts the Data Encryption Key (DEK).

- **Data Encryption Key (DEK)**
  - Generated dynamically by the Encryption Service for each specific SecretVersion.
  - Unique to a single payload; never reused across different secrets or versions.
  - Encrypted by the MEK. The *encrypted* DEK is persisted in the database.
  - Purpose: Encrypts and decrypts the plaintext credential payload.

### 3. Cryptographic Primitives
- **Algorithm**: `AES-256-GCM` (Advanced Encryption Standard in Galois/Counter Mode).
- **Security Properties**: Provides Authenticated Encryption with Associated Data (AEAD), ensuring both confidentiality and integrity/authenticity of the ciphertext.
- **Nonce/IV**: A 96-bit (12-byte) cryptographically secure random nonce must be generated uniquely for every encryption operation.
- **Additional Authenticated Data (AAD)**: An `encryption_context` containing the `secret_id` and `resource_id` should be bound to the payload via AAD to prevent ciphertext swapping attacks.

### 4. Core Cryptographic Flows

#### 4.1 Encryption Flow (Write)
1. **DEK Generation**: Encryption Service generates a secure random 256-bit DEK.
2. **Payload Encryption**: Encryption Service encrypts the plaintext using the DEK, `AES-256-GCM`, and a fresh Nonce, binding the `encryption_context` as AAD.
3. **DEK Encryption**: Encryption Service delegates to the Key Provider abstraction to encrypt the DEK using the active MEK.
4. **Metadata Construction**: The resulting ciphertext, encrypted DEK, MEK `key_version`, `algorithm`, `nonce`, and `encryption_context` are packaged into the `SecretMetadata` value object.
5. **Memory Wipe**: Plaintext DEK and payload are marked for immediate memory clearance.

#### 4.2 Decryption Flow (Read)
1. **Extraction**: Vault Service passes the `SecretMetadata` and `ciphertext` to the Encryption Service.
2. **DEK Decryption**: Encryption Service delegates to the Key Provider abstraction, passing the `encrypted_dek` and `key_version` to retrieve the plaintext DEK.
3. **Payload Decryption**: Encryption Service decrypts the ciphertext using the DEK, the recorded `nonce`, and validating the `encryption_context` via AAD validation.
4. **Return**: The plaintext is returned to the Vault Application Service for API transmission.
5. **Memory Wipe**: Plaintext DEK and payload are marked for immediate memory clearance once transmission completes.

### 5. Key Provider Abstraction
To support future migrations (Phase 2+ KMS integration), the Encryption Service interacts with keys via an abstract interface:

```python
class MasterKeyProvider(Protocol):
    def encrypt_dek(self, plaintext_dek: bytes, key_version: str) -> bytes: ...
    def decrypt_dek(self, encrypted_dek: bytes, key_version: str) -> bytes: ...
    def get_active_key_version(self) -> str: ...
    def supports_key_version(self, key_version: str) -> bool: ...
```
For Phase 1, a `LocalEnvironmentKeyProvider` will be implemented, reading the MEK from a securely injected environment variable.

### 6. Rotation Strategy
Rotation applies to two distinct lifecycles:
1. **Payload Rotation (Credential Change)**: A new `SecretVersion` is created. A completely new DEK is generated and encrypted using the currently active MEK. The `vault_secrets.current_version_id` pointer is updated.
2. **MEK Rotation (Master Key Change)**: The external MEK is updated, establishing a new `key_version`. Existing `encrypted_dek` values remain encrypted by the old MEK. As secrets are accessed or via a background job, the `encrypted_dek` can be decrypted with the old MEK and re-encrypted with the new MEK without ever decrypting the `ciphertext` payload.

### 7. Cryptographic Exceptions and Failure Handling
- **`DecryptionFailedError`**: Raised if AES-GCM tag verification fails (indicating tampering) or if the DEK cannot be decrypted. The operation MUST safely abort and publish a `SecretAccessDenied` event.
- **`MasterKeyUnavailableError`**: Raised if the external Key Provider is unreachable. The Vault goes into a fail-safe mode where read/write operations gracefully fail with a `503 Service Unavailable`.
- **`InvalidKeyVersionError`**: Raised if a payload requires an MEK version that has been securely revoked or destroyed by administrators.

### 8. Secure Memory Handling
Python (`CPython`) does not guarantee deterministic memory wiping due to its garbage collector and string interning behaviors. To mitigate this:
1. Cryptographic operations should utilize `bytes` or `bytearray` (mutable memory).
2. Mutable buffers containing plaintext payloads or DEKs should be explicitly overwritten with zeros (e.g., `buffer[:] = b'\x00' * len(buffer)`) immediately after their required use.
3. Plaintext lifetime shall be strictly minimized in the API routing layer.

### 9. Threat Considerations
- **Ciphertext Swapping**: Mitigated by binding the `secret_id` and `resource_id` into the AAD / `encryption_context`.
- **Timing Attacks**: Mitigated by utilizing standard C-backed cryptographic libraries (e.g., `cryptography` package) which implement constant-time comparison algorithms.
- **Key Extraction**: Mitigated by isolating the MEK to the Key Provider boundary, ensuring it never touches the database layer.
