import requests
from playwright.sync_api import Page, expect


def test_rbac_security_denied(e2e_page: Page, e2e_base_url: str, browser):
    # requester_no_vault valid login
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_no_vault")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")
    expect(e2e_page).to_have_url(e2e_base_url + "/dashboard")

    # Needs approved Access Request first to prove RBAC blocks even if AR is approved.
    # However, creating AR might also be restricted depending on role, but assuming they can request.
    token = e2e_page.evaluate("localStorage.getItem('opsforge_token')")

    # We will simulate an API call directly to retrieve the secret to prove the backend enforces RBAC
    # because the frontend will block navigation to /vault/secrets.

    # BROWSER ASSERTION: Frontend RBAC enforcement
    e2e_page.goto(e2e_base_url + "/vault/secrets")
    # Should redirect to 403 or dashboard
    expect(e2e_page).not_to_have_url(e2e_base_url + "/vault/secrets")

    # We need the secret ID from the database to test the API directly.
    # Assuming seed_e2e created a secret. We can fetch it using admin token.
    admin_context = browser.new_context(base_url=e2e_base_url)
    admin_page = admin_context.new_page()
    admin_page.goto(e2e_base_url + "/login")
    admin_page.fill("#username", "admin_user")
    admin_page.fill("#password", "testpassword")
    admin_page.click("button[type='submit']")

    admin_token = admin_page.evaluate("localStorage.getItem('opsforge_token')")
    admin_context.close()

    api_url = e2e_base_url
    secrets_resp = requests.get(
        f"{api_url}/api/v1/vault/secrets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert secrets_resp.status_code == 200
    secrets = secrets_resp.json().get("data", [])

    if secrets:
        secret_id = secrets[0]["id"]

        # API ASSERTION: Backend RBAC enforcement
        # Attempt to retrieve as requester_no_vault
        retrieve_resp = requests.post(
            f"{api_url}/api/v1/vault/secrets/{secret_id}/retrieve",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Should be 403 Forbidden
        assert retrieve_resp.status_code == 403

        # Check audit logs (as admin)
        audit_resp = requests.get(
            f"{api_url}/api/v1/audit/",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert audit_resp.status_code == 200
        logs = str(audit_resp.json())
        assert "SECRET_RETRIEVAL_FAILED" in logs
        assert "RBAC Denied" in logs


def test_rbac_security_allowed(e2e_page: Page, e2e_base_url: str):
    # requester_vault_read valid login
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")
    expect(e2e_page).to_have_url(e2e_base_url + "/dashboard")

    # Navigate to /vault/secrets
    e2e_page.goto(e2e_base_url + "/vault/secrets")
    expect(e2e_page).to_have_url(e2e_base_url + "/vault/secrets")

    # Ensure they can see the secret list
    expect(
        e2e_page.locator("h1.text-3xl.font-bold").filter(has_text="Secrets")
    ).to_be_visible()

    # Note: Full Reveal test with AR approval is handled in test_checkout_lifecycle.py
