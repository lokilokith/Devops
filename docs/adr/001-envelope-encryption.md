# ADR 001: Envelope Encryption Architecture
**Status:** Accepted
**Date:** 2026-08-04

## Context
The Vault must encrypt highly sensitive credentials at rest. Storing a single Master Key in memory or using it directly for all payload operations limits rotation flexibility and increases the blast radius of key exposure.

## Decision
We will use a two-tier Envelope Encryption architecture. A unique Data Encryption Key (DEK) will be generated for every secret version to encrypt the payload. The DEK will then be encrypted by an external Master Encryption Key (MEK) via an abstract Key Provider interface.

## Consequences
- **Positive:** Enables painless payload rotation and seamless Master Key rotation without needing to decrypt the underlying secret material.
- **Positive:** Reduces the exposure of the MEK.
- **Negative:** Adds complexity to the cryptographic flow and metadata persistence (`key_version`, `encrypted_dek`).
