import os

import pytest

# We assume the frontend is running on localhost:8082 during E2E testing
FRONTEND_URL = os.getenv("E2E_FRONTEND_URL", "http://localhost:8082")


@pytest.fixture(scope="session")
def e2e_base_url():
    """Returns the base URL for the E2E frontend."""
    return FRONTEND_URL


@pytest.fixture(scope="function")
def e2e_context(browser):
    """Provides a fresh, isolated browser context for each test."""
    context = browser.new_context(
        base_url=FRONTEND_URL,
        viewport={"width": 1280, "height": 720},
        # Ensure we don't save traces by default for plaintext tests unless configured
        record_video_dir=None,
    )
    yield context
    context.close()


@pytest.fixture(scope="function")
def e2e_page(e2e_context):
    """Provides a fresh page within the isolated context."""
    page = e2e_context.new_page()
    yield page
    page.close()


@pytest.fixture(autouse=True, scope="function")
def seed_database():
    """
    Reset and seed the E2E database before each test.
    This ensures deterministic behavior for every test.
    """
    import subprocess
    import sys

    # Run the seed_e2e.py script as a subprocess with the correct E2E database URL
    env = os.environ.copy()
    env["DATABASE_URL"] = (
        "postgresql://e2e_user:e2e_password@localhost:5441/opsforge_e2e_db"
    )
    seed_script_path = os.path.join(os.path.dirname(__file__), "seed_e2e.py")
    result = subprocess.run(
        [sys.executable, seed_script_path], env=env, capture_output=True, text=True
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to seed E2E database: {result.stderr}")

    # Wait for the backend container to recover and be reachable
    import time

    import requests

    api_url = FRONTEND_URL.replace("8082", "8081")
    max_retries = 30
    for i in range(max_retries):
        try:
            # Check the health endpoint
            resp = requests.get(f"{api_url}/health", timeout=1)
            if resp.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    else:
        pytest.fail("Backend did not become reachable after seeding")
