# OpsForge Target Environment Reproduction & Operational Guide

## Overview

Phase 2 establishes a disposable Linux SSH target environment and fixed-path root helper boundary for OpsForge PAM target administration.

## Target Architecture

```
OpsForge Worker
      ↓ (SSH over isolated network)
Verified Host Identity (Ed25519 / RSA)
      ↓
opsforge-svc (Bootstrap Identity, password locked)
      ↓ (sudo /usr/local/sbin/opsforge-helper ONLY)
/usr/local/sbin/opsforge-helper (root:root, mode 0750)
      ↓ (Validated Operations)
Protected Manifest (/var/lib/opsforge/ownership_manifest.json, mode 0600)
      ↓
Target-Local Audit Log (/var/log/opsforge-helper.log, mode 0600)
```

## Reproducing the Target from Scratch

### 1. Build and Launch Disposable Target
```powershell
docker compose -f docker-compose.target.yml up -d --build
```

### 2. Verify Container Health
```powershell
docker ps --filter "name=opsforge-disposable-target"
```

### 3. Teardown / Clean Reset
```powershell
docker compose -f docker-compose.target.yml down -v
```

## Security Invariants

1. **Bootstrap Key Isolation**: The `opsforge-svc` private key is strictly a test fixture for the disposable target and is never used with production assets.
2. **Restricted Sudoers Boundary**: `/etc/sudoers.d/opsforge-svc` permits executing ONLY `/usr/local/sbin/opsforge-helper` with NOPASSWD. No shell, compiler, or arbitrary binary execution.
3. **Protected Manifest**: Ownership manifest at `/var/lib/opsforge/ownership_manifest.json` is owned by `root:root` with mode `0600`. The helper is the only writer. System accounts (`root`, `bin`, `daemon`, `opsforge-svc`, etc.) cannot be registered or removed.
4. **Sudoers Safety**: All JIT grant drop-ins are generated from an allowlisted catalog, written to temporary files, set to `0440` `root:root`, verified via `visudo -c -f`, and atomically renamed.
5. **Fail-Closed Host Identity**: SSH connections verify remote host key against registered trusted host key fingerprints, preventing MITM.
