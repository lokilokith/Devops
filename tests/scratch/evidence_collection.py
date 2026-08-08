import asyncio
from playwright.async_api import async_playwright
import json
import os
import psycopg2

artifact_dir = r"C:\Users\lokil\.gemini\antigravity\brain\11670e06-4fe6-4b24-bb87-fa5ffce11e00\scratch"
os.makedirs(artifact_dir, exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        network_log = []
        
        async def handle_request(request):
            network_log.append({
                "type": "request",
                "method": request.method,
                "url": request.url,
                "post_data": request.post_data
            })
            
        async def handle_response(response):
            try:
                body = await response.text()
            except:
                body = "<binary or missing>"
            network_log.append({
                "type": "response",
                "status": response.status,
                "url": response.url,
                "body": body[:500] # just snag the first 500 chars
            })

        page.on("request", handle_request)
        page.on("response", handle_response)

        print("Navigating to login...")
        await page.goto("http://localhost/login")
        await page.fill("input#username", "admin")
        await page.fill("input#password", "secret123")
        await page.click("button[type='submit']")
        await page.wait_for_url("**/dashboard")
        print("Logged in as admin.")

        print("Navigating to users...")
        await page.click("a[href='/users']")
        await page.wait_for_selector("text=Users")

        # Create user 1
        print("Creating user 1...")
        await page.click("button:has-text('Create User')")
        await page.wait_for_selector("div[role='dialog']")
        await page.screenshot(path=os.path.join(artifact_dir, "create_user_modal.png"))
        
        await page.fill("input[name='employee_id']", "EMP001")
        await page.fill("input[name='username']", "ev_user1")
        await page.fill("input[name='email']", "ev_user1@example.com")
        await page.fill("input[name='full_name']", "Evidence User 1")
        await page.fill("input[name='password']", "password123")
        await page.click("div[role='dialog'] button[type='submit']")
        await asyncio.sleep(2)
        
        print("Refreshing...")
        await page.reload()
        try:
            await page.wait_for_selector("text=ev_user1", timeout=5000)
            print("User 1 visible!")
        except Exception as e:
            print("User 1 not visible in UI!")
        await page.screenshot(path=os.path.join(artifact_dir, "users_table_after_1.png"))

        # Create user 2
        print("Creating user 2...")
        await page.click("button:has-text('Create User')")
        await page.wait_for_selector("div[role='dialog']")
        await page.fill("input[name='employee_id']", "EMP002")
        await page.fill("input[name='username']", "ev_user2")
        await page.fill("input[name='email']", "ev_user2@example.com")
        await page.fill("input[name='full_name']", "Evidence User 2")
        await page.fill("input[name='password']", "password123")
        await page.click("div[role='dialog'] button[type='submit']")
        await asyncio.sleep(2)
        
        print("Refreshing...")
        await page.reload()

        # Create user 3
        print("Creating user 3...")
        await page.click("button:has-text('Create User')")
        await page.wait_for_selector("div[role='dialog']")
        await page.fill("input[name='employee_id']", "EMP003")
        await page.fill("input[name='username']", "ev_user3")
        await page.fill("input[name='email']", "ev_user3@example.com")
        await page.fill("input[name='full_name']", "Evidence User 3")
        await page.fill("input[name='password']", "password123")
        await page.click("div[role='dialog'] button[type='submit']")
        await asyncio.sleep(2)
        
        print("Refreshing...")
        await page.reload()

        # Delete user 1
        print("Deleting user 1...")
        try:
            row = page.locator("tr", has_text="ev_user1")
            await row.locator("button").first.click()
            await page.click("text=Delete User")
            await page.click("button:has-text('Delete')")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Failed to delete user 1: {e}")

        print("Refreshing after delete...")
        await page.reload()
        await asyncio.sleep(1)

        # Create user 1 again with same credentials
        print("Recreating user 1...")
        await page.click("button:has-text('Create User')")
        await page.wait_for_selector("div[role='dialog']")
        await page.fill("input[name='employee_id']", "EMP001")
        await page.fill("input[name='username']", "ev_user1")
        await page.fill("input[name='email']", "ev_user1@example.com")
        await page.fill("input[name='full_name']", "Evidence User 1")
        await page.fill("input[name='password']", "password123")
        await page.click("div[role='dialog'] button[type='submit']")
        await asyncio.sleep(2)

        print("Refreshing...")
        await page.reload()
        await asyncio.sleep(1)

        # Bug 2: Access Request
        print("Navigating to Access Requests to request access...")
        await page.click("a[href='/access-requests']")
        await page.wait_for_selector("text=My Access Requests")
        
        print("Creating Access Request for SOC Analyst...")
        try:
            await page.click("button:has-text('Request Access')")
            await page.wait_for_selector("div[role='dialog']")
            
            # Select the role in the form
            # Assuming there is a select or combobox for requested_role_id
            await page.click("button[role='combobox']") # open dropdown
            await page.click("text=SOC Analyst")
            
            await page.fill("textarea[name='business_justification']", "Evidence test")
            await page.click("div[role='dialog'] button[type='submit']")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Failed to create request: {e}")

        print("Navigating to Approval Queue...")
        await page.click("a[href='/approvals']")
        await page.wait_for_selector("text=Approval Queue")
        await page.screenshot(path=os.path.join(artifact_dir, "approval_queue.png"))

        with open(os.path.join(artifact_dir, "network_log.json"), "w") as f:
            json.dump(network_log, f, indent=2)
            
        await browser.close()
        print("Evidence collection complete.")
        
        # Check database
        try:
            conn = psycopg2.connect("postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db")
            cur = conn.cursor()
            cur.execute("SELECT username, email FROM users WHERE username LIKE 'ev_user%'")
            users = cur.fetchall()
            print(f"Users in DB: {users}")
            
            cur.execute("SELECT r.role_name, ar.status, aw.approval_level FROM access_requests ar JOIN roles r ON ar.requested_role_id = r.id JOIN approval_workflows aw ON aw.access_request_id = ar.id ORDER BY ar.created_at DESC LIMIT 1")
            reqs = cur.fetchall()
            print(f"Latest Request in DB: {reqs}")
            conn.close()
        except Exception as e:
            print(f"DB Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
