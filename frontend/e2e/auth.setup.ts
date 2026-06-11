
import { test as setup, expect } from "@playwright/test";
import path from "path";

const authFile = path.join(__dirname, "../.playwright/.auth/user.json");

/**
 * Authentication setup - runs before all tests.
 *
 * This creates an authenticated session that other tests can reuse.
 */
setup("authenticate", async ({ page }) => {
  // Test credentials - adjust for your environment
  const testEmail = process.env.TEST_USER_EMAIL || "admin@example.com";
  const testPassword = process.env.TEST_USER_PASSWORD || "admin1234";

  // Clear any existing auth state to ensure fresh login
  await page.goto("/login");
  await page.evaluate(() => localStorage.removeItem("auth-storage"));

  // Fill in login form
  await page.getByLabel(/email/i).fill(testEmail);
  await page.getByLabel(/password/i).fill(testPassword);

  // Submit form
  await page.getByRole("button", { name: /sign in|log in|login/i }).click();

  // Wait for redirect to dashboard (only happens after successful auth + localStorage set)
  await page.waitForURL(/dashboard/, { timeout: 15000 });

  // Wait for auth store to persist user to localStorage
  await page.waitForFunction(
    () => {
      const raw = localStorage.getItem("auth-storage");
      if (!raw) return false;
      try {
        const state = JSON.parse(raw);
        return state?.state?.user !== null && state?.state?.isAuthenticated === true;
      } catch {
        return false;
      }
    },
    { timeout: 10000 },
  );

  // Dismiss the cookie banner so it doesn't intercept clicks in tests
  await page.evaluate(() => {
    localStorage.setItem(
      "cookie.consent",
      JSON.stringify({
        essential: true,
        analytics: false,
        functional: false,
        decided_at: new Date().toISOString(),
      }),
    );
  });

  // Save authentication state
  await page.context().storageState({ path: authFile });
});
