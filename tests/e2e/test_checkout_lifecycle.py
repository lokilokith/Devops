import requests
import sqlalchemy as sa
from playwright.sync_api import Page, expect
from sqlalchemy import text


def test_checkout_lifecycle_and_checkin(e2e_page: Page, e2e_base_url: str, browser):
    # This test attempts to follow the UI flow for checkout and asserts backend state,
    # then uses the backend API for check-in (since UI is absent).

    # 1. Login as requester_vault_read
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")
    expect(e2e_page).to_have_url(e2e_base_url + "/dashboard")
    token = e2e_page.evaluate("localStorage.getItem('opsforge_token')")

    # Needs an approved Access Request for the policy engine/checkout
    # Let's create one via API for speed, then approve it via API as admin
    api_url = e2e_base_url

    admin_context = browser.new_context(base_url=e2e_base_url)
    admin_page = admin_context.new_page()
    admin_page.goto(e2e_base_url + "/login")
    admin_page.fill("#username", "admin_user")
    admin_page.fill("#password", "testpassword")
    admin_page.click("button[type='submit']")
    admin_token = admin_page.evaluate("localStorage.getItem('opsforge_token')")
    admin_context.close()

    engine = sa.create_engine(
        "postgresql://e2e_user:e2e_password@localhost:5441/opsforge_e2e_db"
    )
    with engine.connect() as conn:
        secret_id = conn.execute(text("SELECT id FROM vault_secrets LIMIT 1")).scalar()
        resource_id = conn.execute(
            text("SELECT resource_id FROM vault_secrets LIMIT 1")
        ).scalar()

    # Create AR
    ar_resp = requests.post(
        f"{api_url}/api/v1/access-requests/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "requested_resource_id": str(resource_id),
            "business_justification": "E2E Checkout test",
            "priority": "low",
        },
    )
    ar_id = ar_resp.json()["data"]["id"]

    # Approve AR as admin
    # First get the workflow id
    with engine.connect() as conn:
        wf_id = conn.execute(
            text("SELECT id FROM approval_workflows WHERE access_request_id = :ar_id"),
            {"ar_id": ar_id},
        ).scalar()
    requests.post(
        f"{api_url}/api/v1/approval-workflows/{wf_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"comments": "Approved for E2E"},
    )

    # 2. Navigate to /vault/secrets and Reveal Secret
    e2e_page.goto(e2e_base_url + "/vault/secrets")

    row = e2e_page.locator("tr", has_text="DB_PROD_PASS").first
    row.locator("button:has(.lucide-more-horizontal)").click()
    e2e_page.click("div[role='menuitem']:has-text('Reveal Secret')")

    # Wait for the modal and verify the secret is shown (we use a regex/check for transient presence)
    # Security Requirement: NEVER assert against the plaintext credential to prevent leaking it in logs.
    expect(e2e_page.locator("text=Secret Payload")).to_be_visible()
    # Check that a copy button exists in the dialog, implying a value was rendered
    expect(e2e_page.locator("button:has-text('Copy')").first).to_be_visible()

    # 3. VERIFY DATABASE STATE: ACTIVE lease and CHECKED_OUT secret
    with engine.connect() as conn:
        secret_status = conn.execute(
            text("SELECT status FROM vault_secrets WHERE id = :sid"), {"sid": secret_id}
        ).scalar()
        lease = conn.execute(
            text(
                "SELECT id, status FROM credential_leases WHERE vault_secret_id = :sid AND access_request_id = :arid"
            ),
            {"sid": secret_id, "arid": ar_id},
        ).fetchone()

    # THESE ASSERTIONS WILL FAIL IF THE FRONTEND/BACKEND ARE NOT WIRED TO CHECKOUTSERVICE
    assert secret_status == "CHECKED_OUT", "Secret should be in CHECKED_OUT state"
    assert lease is not None, "A CredentialLease should have been created"
    assert lease[1] == "ACTIVE", "CredentialLease should be ACTIVE"
    lease_id = lease[0]

    # 4. Perform check-in through the real API
    checkin_resp = requests.post(
        f"{api_url}/api/v1/checkout/checkin/{lease_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert checkin_resp.status_code == 200

    # 5. Verify database state after check-in
    with engine.connect() as conn:
        secret_status_after = conn.execute(
            text("SELECT status FROM vault_secrets WHERE id = :sid"), {"sid": secret_id}
        ).scalar()
        lease_status_after = conn.execute(
            text("SELECT status FROM credential_leases WHERE id = :lid"),
            {"lid": lease_id},
        ).scalar()

    assert secret_status_after == "ROTATING", "Secret should be ROTATING after check-in"
    assert lease_status_after == "RETURNED", "Lease should be RETURNED after check-in"
