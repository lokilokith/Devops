from playwright.sync_api import Page, expect


def test_approval_workflow(e2e_page: Page, e2e_base_url: str, browser):
    # Context 1: Requester creates a request
    e2e_page.goto(e2e_base_url + "/login")
    e2e_page.fill("#username", "requester_vault_read")
    e2e_page.fill("#password", "testpassword")
    e2e_page.click("button[type='submit']")

    e2e_page.goto(e2e_base_url + "/access-requests")
    e2e_page.get_by_role("button", name="Request Access").click()

    e2e_page.click("button[role='combobox']:near(:text('Request Type'))")
    e2e_page.click("div[role='option']:has-text('Resource')")

    e2e_page.click("button[role='combobox']:near(:text('Resource'))")
    e2e_page.click("div[role='option']:has-text('E2E Database Password')")

    e2e_page.fill(
        "textarea[name='business_justification']", "E2E Testing valid access request."
    )
    e2e_page.click("button[type='submit']:has-text('Submit Request')")

    # Wait for creation to finish
    expect(
        e2e_page.locator("div[role='status']").filter(
            has_text="Access request created successfully."
        )
    ).to_be_visible()

    # Context 2: Approver logs in independently
    approver_context = browser.new_context(base_url=e2e_base_url)
    approver_page = approver_context.new_page()

    approver_page.goto(e2e_base_url + "/login")
    approver_page.fill("#username", "approver_user")
    approver_page.fill("#password", "testpassword")
    approver_page.click("button[type='submit']")

    approver_page.goto(e2e_base_url + "/approvals")

    # BROWSER ASSERTION: Request should be visible to approver
    row = approver_page.locator("tr:has-text('PENDING')").first
    expect(row).to_be_visible()

    # Open Actions Menu
    row.locator("button:has(.lucide-more-horizontal)").click()

    # Click Approve
    approver_page.click("div[role='menuitem']:has-text('Approve')")

    # ConfirmDialog opens
    expect(approver_page.locator("text=Approve Request")).to_be_visible()
    approver_page.click("button:has-text('Approve')")

    # BROWSER ASSERTION: Should show success
    expect(
        approver_page.locator("div[role='status']").filter(has_text="Request approved.")
    ).to_be_visible()

    approver_context.close()

    # Back to Context 1 (Requester) - refresh and see APPROVED
    e2e_page.reload()
    expect(e2e_page.locator("tr:has-text('APPROVED')").first).to_be_visible()
