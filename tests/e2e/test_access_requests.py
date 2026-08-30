from playwright.sync_api import Page, expect


def test_access_request_create_valid(e2e_page: Page, e2e_base_url: str):
    # Login
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")
    expect(e2e_page).to_have_url(e2e_base_url + "/dashboard")

    # Navigate to Access Requests
    e2e_page.goto(e2e_base_url + "/access-requests")
    expect(
        e2e_page.locator("h2.text-3xl.font-bold").filter(has_text="My Access Requests")
    ).to_be_visible()

    # Click "Request Access"
    e2e_page.get_by_role("button", name="Request Access").click()

    # Modal opens
    expect(e2e_page.locator("text=Request Access").nth(0)).to_be_visible()

    # Select Resource
    e2e_page.locator("label:has-text('Request Type') ~ button[role='combobox']").click()
    e2e_page.get_by_role("option", name="Resource", exact=True).click()

    # Select the specific resource (DB_PROD_PASS)
    e2e_page.locator("label:has-text('Resource') ~ button[role='combobox']").click()
    e2e_page.get_by_role("option", name="E2E Database Password", exact=True).click()

    # Priority default is low, leave it.

    # Fill Justification
    e2e_page.fill(
        "textarea[name='business_justification']", "E2E Testing valid access request."
    )

    # Submit
    e2e_page.click("button[type='submit']:has-text('Submit Request')")

    # BROWSER ASSERTION: Should see success toast and PENDING in datatable
    expect(
        e2e_page.get_by_text("Access request created successfully.").first
    ).to_be_visible()

    # Ensure PENDING is visible for our new request
    expect(e2e_page.get_by_text("PENDING").first).to_be_visible()


def test_access_request_invalid(e2e_page: Page, e2e_base_url: str):
    # Login
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")
    expect(e2e_page).to_have_url(e2e_base_url + "/dashboard")

    # Navigate to Access Requests
    e2e_page.goto(e2e_base_url + "/access-requests")
    e2e_page.get_by_role("button", name="Request Access").click()

    # Try to submit without justification (HTML5 validation should block)
    # Just clicking submit without filling justification
    # The submit button should be disabled if no role/resource is selected
    expect(e2e_page.get_by_role("button", name="Submit Request")).to_be_disabled()
