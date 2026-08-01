# Security Policy

## Supported Versions

Only the latest release branch is currently supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| v1.0.x  | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it privately. **Do not create public issues for security vulnerabilities.**

Please email security@opsforge.internal with the following details:
- A description of the vulnerability.
- Steps to reproduce the issue.
- Potential impact and any suggested mitigations.

We will acknowledge receipt of your vulnerability report within 48 hours and strive to send you regular updates about our progress.

## Security Practices

Our development process includes:
- SAST (Bandit) and SCA (Safety) scanning on every pull request.
- Mutation testing to ensure security controls (authorization decorators and service-layer validation) are not bypassed.
- Minimum 85% test coverage requirement, with 90% enforced for security-critical modules.
- Principle of Least Privilege implemented via strict RBAC.

## Security Regression Suite

We maintain a dedicated test suite (`tests/regression/`) that characterizes all historical vulnerabilities (e.g., API1 BOLA, API4 Resource Consumption, JWT Revocation issues). Any proposed change that causes a regression test to fail will be automatically rejected by the CI/CD pipeline.
