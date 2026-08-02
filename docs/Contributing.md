# Contributing to OpsForge

Thank you for your interest in contributing to OpsForge!

## Development Workflow
1. Fork the repository.
2. Create a feature branch: git checkout -b feat/your-feature-name
3. Make your changes.
4. Ensure all code is formatted and passes linting:
   \\\ash
   black app/ tests/
   isort app/ tests/
   ruff check app/ tests/
   \\\
5. Ensure all tests pass:
   \\\ash
   pytest
   \\\
6. Submit a Pull Request targeting the main branch.

## Conventional Commits
Please use Conventional Commit messages (e.g., eat:, ix:, docs:, chore:).
