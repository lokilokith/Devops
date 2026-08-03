import asyncio
from playwright.async_api import async_playwright
import time
import os
import psycopg2

DB_URL = "postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("Navigating to login...")
        await page.goto("http://localhost/login")
        
        await page.fill("input#username", "admin")
        await page.fill("input#password", "secret123")
        await page.click("button[type='submit']")
        await page.wait_for_url("**/dashboard")
        print("Logged in as admin.")

        # ========================================================
        # BUG 1 — USER CREATION FRONTEND FAILURE
        # ========================================================
        print("\n--- Testing Bug 1: User Creation ---")
        await page.click("text=Users")
        await page.wait_for_selector("text=Create User")
        
        # Listen for the POST request to capture payload and response
        user_create_request = None
        user_create_response = None
        async def on_request(request):
            nonlocal user_create_request
            if request.method == "POST" and "/api/v1/users" in request.url:
                user_create_request = request
                
        async def on_response(response):
            nonlocal user_create_response
            if response.request.method == "POST" and "/api/v1/users" in response.url:
                user_create_response = response

        page.on("request", on_request)
        page.on("response", on_response)

        print("Clicking 'Create User' button...")
        await page.click("text=Create User")
        
        await page.fill("input[name='username']", "pw_testuser")
        await page.fill("input[name='email']", "pw_testuser@example.com")
        await page.fill("input[name='full_name']", "Playwright Test User")
        await page.fill("input[name='employee_id']", "PW001")
        await page.fill("input[name='password']", "password123")
        # leave title blank
        
        await page.click("div[role='dialog'] button[type='submit']")
        
        # wait a bit for network
        await asyncio.sleep(2)
        
        if user_create_request:
            print("Captured POST Request Payload:")
            print(user_create_request.post_data)
        
        if user_create_response:
            print(f"Captured POST Response Status: {user_create_response.status}")
            try:
                print("Response body:", await user_create_response.json())
            except:
                print("Response text:", await user_create_response.text())
                
        # Check if user is in table UI
        await asyncio.sleep(1)
        is_visible = await page.is_visible("text=pw_testuser")
        print(f"User visible in UI? {is_visible}")

        # Check DB
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT username, title FROM users WHERE username = 'pw_testuser'")
        row = cur.fetchone()
        print(f"Database row: {row}")
        conn.close()

        # ========================================================
        # BUG 2 — ACCESS REQUEST NOT APPEARING IN APPROVAL QUEUE
        # ========================================================
        print("\n--- Testing Bug 2: Access Request Synchronization ---")
        await page.click("text=My Requests")
        await page.wait_for_selector("text=Request Access")
        
        print("Creating Access Request...")
        await page.click("text=Request Access")
        await page.fill("textarea[name='business_justification']", "PW Testing Frontend Sync")
        await page.click("button:has-text('Submit Request')")
        
        await asyncio.sleep(2)
        
        print("Switching to Approval Queue (without refreshing)...")
        await page.click("text=Approval Queue")
        await asyncio.sleep(2)
        
        # See if "PW Testing Frontend Sync" is in the table
        is_request_visible = await page.is_visible("text=PW Testing Frontend Sync")
        print(f"Request visible in Approval Queue UI immediately? {is_request_visible}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
