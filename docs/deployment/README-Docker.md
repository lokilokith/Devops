# OpsForge Docker Deployment Guide

This document outlines the completely redesigned, production-ready Docker deployment architecture for OpsForge.

## 🏗 Architecture
The deployment consists of three primary services orchestrated via `docker-compose.yml`:
1. **`postgres`**: A PostgreSQL 15 Alpine container persisting data to a named volume.
2. **`backend`**: The Python 3.13 Flask application served via Gunicorn. It automatically runs database migrations (`flask db upgrade`) on startup.
3. **`frontend`**: The React Single Page Application (SPA), compiled via Vite in a Node 22 builder stage and served statically via an optimized Nginx Alpine container.

## 🚀 Getting Started

### 1. Configuration
First, copy the `.env.example` file to create your own `.env` file:
```bash
cp .env.example .env
```
Open `.env` and fill in secure values for `SECRET_KEY` and `JWT_SECRET_KEY`. 
*Note: In `APP_ENV=production`, the application will fail to start (fail-fast) if these secrets are missing.*

### 2. Running Locally (Development)
For local development, you can use the provided override file to bind-mount directories.
```bash
docker compose up --build
```
This command automatically:
1. Provisions the database.
2. Builds the backend and frontend containers.
3. Runs the database migrations automatically via `docker-entrypoint.sh`.
4. Starts the web server.

### 3. Stopping the Application
To gracefully stop the application without destroying your database volume:
```bash
docker compose down
```

### 4. Complete Clean / Reset
If you need to completely wipe the Docker state (including the database volume) and start entirely from scratch:
```bash
docker compose down -v --rmi all --remove-orphans
```

## 🔒 Security & Performance Features
- **Non-Root Execution**: The backend container strictly creates and drops privileges to a dedicated `opsforge` user.
- **Multi-Stage Builds**: Compilers and SDKs (Node, GCC) are entirely stripped from the final runtime images, significantly reducing the attack surface and image size.
- **Fail-Fast Configuration**: The Flask bootloader strictly validates environment variables based on the `APP_ENV`. It will refuse to start and throw a clear `ConfigurationException` rather than silently fallback to insecure defaults in production.
- **Native Healthchecks**: Services utilize Docker's `HEALTHCHECK` directive. `docker-compose.yml` uses `condition: service_healthy` to ensure rigorous boot sequencing (e.g., backend will not start until postgres is ready; frontend will not start until backend is ready).
- **Optimized Nginx**: The frontend is served with aggressive cache headers for static assets (`immutable`) while correctly returning `no-cache` for `index.html` to ensure seamless SPA routing and rapid client updates.

## 🛠 Troubleshooting

**Problem**: Backend container crashes with `Configuration Error: ... environment variable is missing`.
**Solution**: You are attempting to run in `production` mode without providing `SECRET_KEY` or `JWT_SECRET_KEY` in your `.env` file. Fill them in.

**Problem**: The frontend UI shows a 502 Bad Gateway when calling the API.
**Solution**: This usually occurs if the backend container is crash-looping or hasn't finished booting. Check backend logs using `docker compose logs -f backend`.
