from playwright.sync_api import Page, expect


def test_login_valid(e2e_page: Page, e2e_base_url: str):
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")

    # BROWSER ASSERTION: Should redirect to dashboard and show user's avatar or Dashboard header
    expect(e2e_page).to_have_url(e2e_base_url + "/dashboard")
    expect(
        e2e_page.locator("h2.text-3xl.font-bold").filter(has_text="Dashboard")
    ).to_be_visible()


def test_login_invalid(e2e_page: Page, e2e_base_url: str):
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "wrongpassword")
    e2e_page.click("button[type='submit']")

    # BROWSER ASSERTION: Should show error message
    expect(e2e_page.locator("p.text-sm.text-destructive")).to_be_visible()
    expect(e2e_page.locator("p.text-sm.text-destructive")).to_contain_text(
        "Unauthorized"
    )


def test_protected_page_unauthenticated(e2e_page: Page, e2e_base_url: str):
    e2e_page.goto(e2e_base_url + "/vault/secrets")

    # BROWSER ASSERTION: Should redirect to login
    expect(e2e_page).to_have_url(e2e_base_url + "/login")


def test_logout(e2e_page: Page, e2e_base_url: str):
    # Login first
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")
    expect(e2e_page).to_have_url(e2e_base_url + "/dashboard")

    # Use the actual logout button from Header.tsx
    e2e_page.click("button[title='Logout']")

    # BROWSER ASSERTION
    expect(e2e_page).to_have_url(e2e_base_url + "/login")


def test_reuse_session_after_logout(e2e_page: Page, e2e_base_url: str):
    # This requires API/Token intercept since browser localstorage is wiped on logout,
    # but the token shouldn't work on the backend either.
    # E2E test will capture the token, logout, then attempt an API request.

    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")
    expect(e2e_page).to_have_url(e2e_base_url + "/dashboard")

    # Capture local storage token
    token = e2e_page.evaluate("localStorage.getItem('opsforge_token')")
    assert token is not None

    e2e_page.locator("button[title='Logout']").click()

    # Wait for logout API call and redirect to complete
    expect(e2e_page).to_have_url(e2e_base_url + "/login")

    # API ASSERTION: Try using the old token directly against the backend
    import requests

    response = requests.get(
        e2e_base_url + "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    # Depending on implementation, if JWTs are stateless they might still work unless blacklisted.
    # For Phase 2E, we'll assert it's 401. If it returns 200, the test highlights a security defect.
    assert response.status_code == 401
