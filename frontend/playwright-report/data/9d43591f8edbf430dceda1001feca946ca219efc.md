# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: session-control.spec.ts >> Session Control >> should navigate to session control and display real backend state
- Location: e2e\session-control.spec.ts:15:3

# Error details

```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:5173/login
Call log:
  - navigating to "http://localhost:5173/login", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Session Control', () => {
  4  |   test.beforeEach(async ({ page }) => {
  5  |     // 1. Log in
> 6  |     await page.goto('/login');
     |                ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:5173/login
  7  |     await page.fill('input[type="email"]', 'admin@example.com'); // Use default seeded admin
  8  |     await page.fill('input[type="password"]', 'admin');
  9  |     await page.click('button[type="submit"]');
  10 |     
  11 |     // Wait for redirect to dashboard
  12 |     await expect(page).toHaveURL(/.*dashboard/);
  13 |   });
  14 | 
  15 |   test('should navigate to session control and display real backend state', async ({ page }) => {
  16 |     // 2. Navigate to Session Control
  17 |     await page.click('text="Active Sessions"');
  18 |     await expect(page).toHaveURL(/.*sessions/);
  19 | 
  20 |     // 3. Verify page renders correctly
  21 |     await expect(page.locator('h1')).toHaveText('Active Sessions');
  22 |     
  23 |     // 4. Verify that either we have "no sessions" message or a list of session cards
  24 |     // This proves the real backend is responding and the page parses the state
  25 |     const hasNoSessions = await page.locator('text="You have no active privileged sessions."').isVisible();
  26 |     const hasSessionCards = await page.locator('.grid > .rounded-xl').count() > 0;
  27 |     
  28 |     expect(hasNoSessions || hasSessionCards).toBeTruthy();
  29 |     
  30 |     // Day 4 will implement the full e2e lifecycle (request -> approve -> activate -> terminate)
  31 |     // For Day 3, we simply prove the foundation reaches the backend and renders.
  32 |   });
  33 | });
  34 | 
```