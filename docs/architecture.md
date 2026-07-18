# Architecture Blueprint - OpsForge

This document captures the frozen architectural model for OpsForge. The codebase is intentionally split into infrastructure, shared utilities, domain concepts, and isolated feature packages.

## Layering Model

```text
Routes -> Services -> Repositories -> Models -> Database
```

Infrastructure, shared helpers, and domain concepts may be imported by features. Feature packages must not import one another’s internal implementation.

## Package Responsibilities

### `platform/`
Infrastructure only. This package owns configuration, extension initialization, logging, middleware, lifecycle hooks, and security scaffolding.

### `shared/`
Reusable cross-cutting helpers, including database access, exceptions, validators, schemas, responses, decorators, helpers, and utilities.

### `domain/`
Business concepts only. This package is reserved for constants, enums, events, interfaces, and policies with no Flask or SQLAlchemy dependency.

### Feature Packages
`identity/`, `roles/`, `resources/`, `access/`, `approval/`, and `audit/` are symmetrical feature boundaries. Each feature is expected to expose the same internal structure:

```text
feature/
    __init__.py
    models.py
    repository.py
    service.py
    routes.py
    schemas.py
    validators.py
    exceptions.py
```

## Dependency Rules

Allowed dependency path:

```text
Routes -> Services -> Repositories -> Models -> Database
```

Also allowed:
- Feature code -> `shared/`
- Feature code -> `platform/`
- Feature code -> `domain/`

Not allowed:
- Feature-to-feature imports
- Reverse layer dependencies
- Flask or SQLAlchemy code inside `domain/`

## Validation Expectations

Each architecture change should be validated with the full test suite, application startup under `APP_ENV=testing`, and import resolution checks. The repository currently passes the full suite and boots successfully under the testing environment.
