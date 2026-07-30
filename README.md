# OpsForge

OpsForge is a production-quality Flask backend foundation for future enterprise feature work. The repository is intentionally architecture-first: it preserves a clean route -> service -> repository -> model -> database flow while keeping infrastructure, shared utilities, and business concepts separated.

## Architecture Overview

The frozen package layout is:

```text
app/
core/ or platform/   # Infrastructure only: config, extensions, logging, middleware, security, lifecycle
shared/              # Reusable helpers, database access, exceptions, validators, schemas, responses
domain/              # Business concepts only: constants, enums, events, interfaces, policies
identity/            # Feature boundary
roles/               # Feature boundary
resources/           # Feature boundary
access/              # Feature boundary
approval/            # Feature boundary

tests/
docs/
```

`platform/` is the canonical name in this repository. `core/` is documented as an acceptable synonym, but renaming would add churn without improving runtime behavior.

## Folder Responsibilities

- `app/`: application bootstrap and API assembly.
- `platform/`: infrastructure only, including configuration, extension setup, logging, middleware, lifecycle hooks, and security scaffolding.
- `shared/`: reusable cross-cutting code shared across features.
- `domain/`: pure business concepts with no Flask, SQLAlchemy, or RESTX dependencies.
- `identity/`, `roles/`, `resources/`, `access/`, `approval/`, `audit/`: isolated feature packages.
- `tests/`: integration and unit tests for the current architecture.
- `docs/`: architecture and development documentation.

## Dependency Rules

Allowed flow:

Routes -> Services -> Repositories -> Models -> Database

Feature packages may depend on `shared/`, `platform/`, and `domain/`, but never on another feature package’s internal implementation.

## Development Guidelines

- Keep one responsibility per package.
- Prefer singular file names such as `service.py`, `repository.py`, `routes.py`, `schemas.py`, `validators.py`, and `exceptions.py` inside each feature.
- Centralize reusable logic in `shared/`.
- Keep infrastructure code in `platform/`.
- Keep business concepts in `domain/`.
- Preserve the existing layered flow and avoid feature-to-feature imports.

## Feature Module Template

```text
feature_name/
    __init__.py
    models.py
    repository.py
    service.py
    routes.py
    schemas.py
    validators.py
    exceptions.py
```

## Validation

The repository is validated through the full pytest suite and startup checks under `APP_ENV=testing`. Any architecture change should be followed by the same validation sequence before further edits.
- `APP_ENV`: Set to `development`, `testing`, or `production`.

## Docker Deployment (v0.6.0)

OpsForge is fully containerized for both development and production environments.

### Prerequisites
- Docker
- Docker Compose

### Local Development
To run OpsForge with live-reloading and direct PostgreSQL access (port 5432):
```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### Production Deployment
To run OpsForge in a production-like environment (Gunicorn, internal DB, optimized image):
```bash
cp .env.production.example .env
docker compose up -d --build
```

### Useful Commands
- **View logs:** `docker compose logs -f api`
- **Run tests:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm api pytest`
- **Check health:** `curl http://localhost:8000/health/ready`
- **Check version metadata:** `curl http://localhost:8000/version`
