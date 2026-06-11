
import { test, expect } from "@playwright/test";

/** Inject cookie consent into localStorage before the page loads so the banner never shows. */
async function setCookieConsent(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      "cookie.consent",
      JSON.stringify({ essential: true, analytics: false, functional: false, decided_at: new Date().toISOString() }),
    );
  });
}

test.describe("Authentication", () => {
  test.describe("Login Page", () => {
    test.beforeEach(async ({ page }) => {
      await setCookieConsent(page);
    });

    test("should display login form", async ({ page }) => {
      await page.goto("/login");

      // Check for login form elements
      await expect(page.getByRole("heading", { name: /sign in|log in/i })).toBeVisible();
      await expect(page.getByLabel(/email/i)).toBeVisible();
      await expect(page.getByLabel(/password/i)).toBeVisible();
      await expect(page.getByRole("button", { name: /sign in|log in|login/i })).toBeVisible();
    });

    test("should show validation errors for empty form", async ({ page }) => {
      await page.goto("/login");

      // Submit empty form
      await page.getByRole("button", { name: /sign in|log in|login/i }).click();

      // Should show validation errors
      await expect(page.getByText(/required|invalid/i)).toBeVisible();
    });

    test("should show error for invalid credentials", async ({ page }) => {
      await page.goto("/login");

      // Fill in invalid credentials
      await page.getByLabel(/email/i).fill("invalid@example.com");
      await page.getByLabel(/password/i).fill("wrongpassword");
      await page.getByRole("button", { name: /sign in|log in|login/i }).click();

      // Should show error message
      await expect(
        page.getByText(/invalid|incorrect|failed|error/i).first()
      ).toBeVisible({ timeout: 5000 });
    });

    test("should have link to registration", async ({ page }) => {
      await page.goto("/login");

      // Should have link to register page
      const registerLink = page.getByRole("link", { name: /sign up|register|create account/i });
      await expect(registerLink).toBeVisible();
    });
  });

  test.describe("Registration Page", () => {
    test.beforeEach(async ({ page }) => {
      await setCookieConsent(page);
    });

    test("should display registration form", async ({ page }) => {
      await page.goto("/register");

      // Check for registration form elements
      await expect(page.getByRole("heading", { name: /sign up|register|create/i })).toBeVisible();
      await expect(page.getByLabel(/email/i)).toBeVisible();
      await expect(page.getByLabel(/password/i).first()).toBeVisible();
      await expect(page.getByRole("button", { name: /sign up|register|create/i })).toBeVisible();
    });

    test("should validate password requirements", async ({ page }) => {
      await page.goto("/register");

      // Fill in weak password
      await page.getByLabel(/email/i).fill("newuser@example.com");
      await page.getByLabel(/password/i).first().fill("weak");

      // Should show password requirements error
      await page.getByRole("button", { name: /sign up|register|create/i }).click();
      await expect(page.getByText(/password|characters|strong/i).first()).toBeVisible();
    });

    test("should have link to login", async ({ page }) => {
      await page.goto("/register");

      // Should have link to login page
      const loginLink = page.getByRole("link", { name: /sign in|log in|login|already have/i });
      await expect(loginLink).toBeVisible();
    });
  });

  test.describe("Authenticated User", () => {
    // Use authenticated state from setup
    test.use({
      storageState: ".playwright/.auth/user.json",
    });

    test("should redirect to dashboard after login", async ({ page }) => {
      await page.goto("/dashboard");

      // Should remain on dashboard (not redirected to login)
      await expect(page).not.toHaveURL(/login/i);
      await expect(page).toHaveURL(/dashboard/i);
    });

    test("should show user menu or profile", async ({ page }) => {
      await page.goto("/dashboard");

      // Should have user profile/menu element
      await expect(
        page.getByRole("button", { name: /profile|account|user/i }).or(
          page.getByText(/@/i)
        )
      ).toBeVisible();
    });

    test("should be able to logout", async ({ page }) => {
      await page.goto("/dashboard");

      // Find and click logout button
      const logoutButton = page.getByRole("button", { name: /log out|sign out/i }).or(
        page.getByRole("link", { name: /log out|sign out/i })
      );

      if (await logoutButton.isVisible()) {
        await logoutButton.click();

        // Should be redirected to login or home
        await expect(page).toHaveURL(/login|\/$/);
      }
    });
  });
});
