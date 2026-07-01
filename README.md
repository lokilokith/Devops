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

## Future Enhancements
- User and role authentication (RBAC).
- Security logging and SIEM integration.
- Automated pipeline deployment.

## License
MIT License - see `LICENSE` for details.
