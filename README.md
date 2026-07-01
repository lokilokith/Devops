# OpsForge

## Project Overview
OpsForge is a portfolio-quality DevSecOps platform demonstrating how a secure Threat Intelligence Management API is built, containerized, and managed using clean software architecture patterns and modern DevOps workflows.

## Problem Statement
Traditional threat intelligence sharing is often chaotic, unstandardized, and lacking secure workflow controls. OpsForge addresses this by delivering a production-grade api featuring rigorous state-transition rules, comprehensive schemas, database abstraction, and fully integrated API documentation.

## Architecture
The API enforces a unidirectional data flow separating concerns into:
`Client ──> Flask-RESTX Route ──> Service Layer ──> Repository Layer ──> SQLAlchemy Model ──> Database`

## Features
- **Threat Intel CRUD**: Standardized lifecycle management for threat indicators (IP, domain, hash, URL).
- **State Transition Machine**: Enforces secure transitions (Open -> Investigating -> Contained -> Closed). Re-opening ticket states is blocked by business logic.
- **Metrics Intelligence**: Endpoint yielding aggregate metrics for high-level triage insights.
- **Health Telemetry**: Returns service and database status alongside live uptime statistics.
- **Self-Documenting API**: Live Swagger UI exposing endpoint specifications.

## Technology Stack
- **Web Framework**: Flask 3.x
- **API Documentation & Routing**: Flask-RESTX 1.3.x
- **ORM & Database**: SQLAlchemy & PostgreSQL
- **Migrations**: Flask-Migrate & Alembic
- **Formatting & Testing**: Black, Ruff, and Pytest

## Folder Structure
```text
opsforge/
├── app/                  # Application core
│   ├── config/           # Environment configuration loaders
│   ├── models/           # SQLAlchemy schemas & structures
│   ├── routes/           # RESTX namespaces & blueprints
│   ├── schemas/          # Input/output serialization layers
│   ├── services/         # Business logic & Repository implementation
│   ├── utils/            # Global errors & exceptions
│   └── constants.py      # Enums and configuration defaults
├── docs/                 # System documentation blueprints
├── tests/                # Domain-isolated test suites
├── Makefile              # Scaffolding operations
├── pyproject.toml        # Ruff/Black config & packaging metadata
└── requirements.txt      # Core application requirements
```

## Roadmap
- **Phase 1**: Working Python Flask API Scaffold (Current)
- **Phase 2**: Docker containerization & Docker Compose setup
- **Phase 3**: Telemetry exporters (Prometheus & Grafana)
- **Phase 4**: Security scanners (Trivy, Bandit, Gitleaks)
- **Phase 5**: GitHub Actions CI/CD workflows

## Local Development

### 1. Setup Virtual Environment
```bash
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Unix:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configuration & Environment Variables
Copy `.env.example` to `.env` (which is gitignored) and configure variables:
- `APP_ENV`: Set to `development`, `testing`, or `production`.
- `DATABASE_URL`: Connection string (required for `development` and `production`, e.g. `postgresql://user:password@localhost:5432/opsforge`).
- `SECRET_KEY`: Security secret string.

### 4. Application Startup
Start the application using the main entry point:
```bash
# On Windows PowerShell:
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/opsforge"
python run.py

# On Unix:
export APP_ENV="development"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/opsforge"
python run.py
```

### 5. Database Migrations
Migrations are managed via Flask-Migrate and Alembic:
```bash
# Generate a new migration script (e.g. after schema changes)
export APP_ENV="development"
flask db migrate -m "Description of change"

# Apply migrations to database
flask db upgrade
```

## Persistence Layer & Repository Overview
OpsForge decouples data storage definitions from data access logic using the Repository Pattern:
- **Models**: Located in `app/models/threat.py`, defining the core `Threat` table schema, index optimizations, and portable JSON tags column.
- **Repository Interface**: Located in `app/repositories/threat_repository.py`. It communicates with SQLAlchemy to execute CRUD operations (e.g. `create()`, `find_by_id()`, `update()`, `delete()`, `paginate()`).
- **Transaction Isolation**: The repository layer does NOT commit or rollback transactions (leaving boundary management to the service layer).

## Business Layer & Service Overview
The Service Layer coordinates all domain-level and transactional activities:
- **Service Interface**: Located in `app/services/threat_service.py` (`ThreatService`). It orchestrates business workflows and validates indicator values.
- **Validations & Exceptions**: Custom business logic in `app/utils/validators.py` and domain exception classes in `app/utils/exceptions.py` reject invalid inputs (e.g. out-of-bounds confidence rating, invalid threat enums).
- **Transaction Management**: The service layer owns database commits and rollbacks. In case of database operations failure, it automatically rolls back active session transactions and raises `DatabaseOperationException`.
- **Workflow State Machine**: Controls status state transitions strictly according to the defined lifecycle: `Open ──> Investigating ──> Contained/False Positive ──> Closed`.

## REST API Layer & Swagger Overview
The API layer exposes the services via clean HTTP endpoints using **Flask-RESTX**:
- **Swagger Documentation**: Self-documenting API accessible at `/docs` when running the application.
- **Unified JSON Format**:
  - Success Envelope: `{"success": true, "message": "...", "data": {...}}`
  - Failure Envelope: `{"success": false, "message": "...", "errors": [...]}`
- **Exposed Endpoints**:
  - `POST /threats` — Create a new validated threat indicator.
  - `GET /threats` — Retrieve a filtered, sorted, paginated list of indicators.
  - `GET /threats/search` — Search threat indicators by partial match on indicator or source.
  - `GET /threats/<id>` — Retrieve details of a specific indicator.
  - `PUT /threats/<id>` — Overwrite all fields of a threat indicator.
  - `PATCH /threats/<id>/status` — Trigger status lifecycle changes and analyst assignments.
  - `DELETE /threats/<id>` — Delete a threat record.
  - `GET /stats` — Compile operational telemetry dashboard statistics.
  - `GET /health` — Get vitality metrics checking system uptime and database connectivity.

## Future Enhancements
- User and role authentication (RBAC).
- Security logging and SIEM integration.
- Automated pipeline deployment.

## License
MIT License - see `LICENSE` for details.
