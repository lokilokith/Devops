# Testing Strategy

OpsForge employs a comprehensive testing strategy spanning unit tests, integration tests, and mutation testing.

## Pytest Suite
The core test suite is located in 	ests/.
To run tests locally:
\\\ash
pytest --cov=app tests/
\\\
We enforce a strict >85% code coverage threshold.

## Mutation Testing
To ensure the test suite is actively catching bugs (and not just executing code for coverage metrics), OpsForge uses mutmut.
Mutation testing is currently configured to run manually or via nightly workflows due to its execution time.

To run mutation testing locally:
\\\ash
mutmut run
mutmut results
\\\

## Transaction Isolation
Integration tests utilizing db_session are wrapped in nested transactions and utilize db_session.flush() and ollback() via 	ry...finally blocks to guarantee isolation between tests.
