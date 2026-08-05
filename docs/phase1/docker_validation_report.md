# OpsForge PAM Phase 1 — Docker Validation Report

## 1. Current Architecture
- **PostgreSQL**: Stores the main OpsForge schema and Phase 1 Credential Vault schema. Database URL is constructed using variables from the environment file (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`).
- **Backend (Flask/Python)**: Serves the REST API. Contains the Phase 0 modules and Phase 1 modules (Vault Domain, Repository, Encryption Layer, Policy Engine, etc.). Depends on `postgres`.
- **Frontend (React/Vite)**: Static SPA serving the UI. Requests are proxied or directed to the backend API. Depends on `backend` being healthy.

## 2. Expected Deployment Flow
1. `docker compose build --no-cache` builds the containers from scratch.
   - `Dockerfile.backend` installs `requirements.txt` packages and prepares `docker-entrypoint.sh`.
   - `Dockerfile.frontend` installs node modules, builds the Vite production output, and serves it via an Nginx stage.
2. `docker compose up -d` brings up `postgres`.
3. `postgres` reaches a healthy state.
4. `opsforge-backend` starts. The `docker-entrypoint.sh` executes `flask db upgrade` to run all migrations.
5. If `flask db upgrade` succeeds, Gunicorn binds to port 5000 and the python health check passes.
6. `opsforge-frontend` starts once `backend` is healthy.

## 3. Detected Problems
- **Issue 1: Missing Backend Dependency (`cryptography`)**
  - **Error Trace**: 
    ```
    opsforge-backend  | Error: While importing 'run', an ImportError was raised:
    opsforge-backend  | ModuleNotFoundError: No module named 'cryptography'
    opsforge-backend  |     from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ```
  - **Root Cause**: Phase 1 implementation introduced envelope encryption for Vault secrets using `AESGCM`. The `cryptography` Python package was heavily utilized in `app/vault/crypto.py` (and related services) but was never added to `requirements.txt`.
  - **Security Impact**: The Vault subsystem fails to load securely, breaking the entire backend container startup.
  - **Fix Required**: Add `cryptography` to `requirements.txt`.
