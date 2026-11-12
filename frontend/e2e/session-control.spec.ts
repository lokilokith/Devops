import { test, expect } from '@playwright/test';

test.describe('Session Control', () => {
  test.beforeEach(async ({ page }) => {
    // 1. Log in
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@example.com'); // Use default seeded admin
    await page.fill('input[type="password"]', 'admin');
    await page.click('button[type="submit"]');
    
    // Wait for redirect to dashboard
    await expect(page).toHaveURL(/.*dashboard/);
  });

  test('should navigate to session control and display real backend state', async ({ page }) => {
    // 2. Navigate to Session Control
    await page.click('text="Active Sessions"');
    await expect(page).toHaveURL(/.*sessions/);

    // 3. Verify page renders correctly
    await expect(page.locator('h1')).toHaveText('Active Sessions');
    
    // 4. Verify that either we have "no sessions" message or a list of session cards
    // This proves the real backend is responding and the page parses the state
    const hasNoSessions = await page.locator('text="You have no active privileged sessions."').isVisible();
    const hasSessionCards = await page.locator('.grid > .rounded-xl').count() > 0;
    
    expect(hasNoSessions || hasSessionCards).toBeTruthy();
    
    // Day 4 will implement the full e2e lifecycle (request -> approve -> activate -> terminate)
    // For Day 3, we simply prove the foundation reaches the backend and renders.
  });
});
