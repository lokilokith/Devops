# OpsForge 🛡️

[![CI Pipeline](https://img.shields.io/github/actions/workflow/status/lokilokith/Devops/ci.yml?branch=main&label=CI%2FCD&style=flat-square)](https://github.com/lokilokith/Devops/actions)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/lokilokith/Devops/main/coverage.json&style=flat-square)](#)
[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?style=flat-square)](#)
[![Flask](https://img.shields.io/badge/Framework-Flask-black?style=flat-square&logo=flask)](#)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat-square)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![Security: Bandit](https://img.shields.io/badge/security-bandit-yellow.svg?style=flat-square)](https://github.com/PyCQA/bandit)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](https://opensource.org/licenses/MIT)

**OpsForge** is a mature, enterprise-grade DevSecOps Threat Intelligence Management Platform. Designed for modern security operations centers (SOCs) and infrastructure teams, OpsForge provides centralized resource governance, strict Role-Based Access Control (RBAC), and automated approval workflows.

## 🚀 Features
- **Strict RBAC & Governance**: Granular, role-based access to security resources and API endpoints.
- **DevSecOps Integrations**: Native threat intelligence workflow handling.
- **Enterprise Security**: Production-ready JWT authentication, CORS, rate limiting, and SAST/SCA hardening.
- **Audit Logging & Notifications**: Complete observability of system mutations.

## 🏗 Architecture
OpsForge follows a clean architecture pattern within a modular Flask monorepo.

<!-- Architecture diagram goes here -->

## 🛠 Tech Stack
- **Backend**: Python 3.11+, Flask, Flask-RESTX, SQLAlchemy
- **Database**: SQLite (Development) / PostgreSQL (Production)
- **CI/CD**: GitHub Actions (Pytest, Mutmut, Bandit, Safety, Ruff)
- **Infrastructure**: Docker & Docker Compose

## 📚 Documentation
Comprehensive documentation is available in the docs/ directory:
- [System Architecture](docs/Architecture.md)
- [API Design & Swagger](docs/API.md)
- [Local Development Guide](docs/Development.md)
- [Testing & Mutation Strategies](docs/Testing.md)
- [Deployment Guide](docs/Deployment.md)
- [Security Model & RBAC](docs/Security.md)

## ⚙️ Installation & Local Development

### Using Docker (Recommended)
`ash
git clone https://github.com/lokilokith/Devops.git
cd Devops/opsforge
docker-compose up --build
`
The API will be available at http://localhost:5000/api/v1/.

### Manual Setup
`ash
python -m venv venv
source venv/bin/activate
pip install -e .[dev]
flask run
`

## 🧪 Testing & CI/CD
OpsForge maintains >85% code coverage and utilizes mutation testing for strict security guarantees.
`ash
pytest --cov=app tests/
mutmut run
`

## 🛡 Security Scanning
`ash
bandit -r app/
safety check -r requirements.txt
pip-audit -r requirements.txt
`

## 🤝 Contributing
Please review our [Contributing Guidelines](docs/Contributing.md) before submitting pull requests.

## 📝 License
Distributed under the MIT License. See LICENSE for more information.