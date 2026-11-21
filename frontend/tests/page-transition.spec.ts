import { test, expect } from "@playwright/test";

test.describe("Page Change Transition", () => {
  test("renders .page-transition wrapper and animates main content with compositor properties", async ({ page }) => {
    await page.goto("/login");

    // The root Template should render the page-transition container
    const pageTransition = page.locator(".page-transition");
    await expect(pageTransition).toBeVisible();

    // The main element should exist inside the page transition container
    const main = pageTransition.locator("main");
    await expect(main).toBeVisible();

    // Verify CSS animation uses compositor-friendly properties
    const animationName = await main.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return styles.animationName;
    });
    expect(animationName).toContain("pageEnter");

    // Verify duration is within 200–350ms specification
    const animationDuration = await main.evaluate((el) => {
      return parseFloat(window.getComputedStyle(el).animationDuration);
    });
    expect(animationDuration).toBeGreaterThanOrEqual(0.2);
    expect(animationDuration).toBeLessThanOrEqual(0.35);

    // Verify will-change includes compositor properties
    const willChange = await main.evaluate((el) => {
      return window.getComputedStyle(el).willChange;
    });
    expect(willChange).toMatch(/opacity|transform/);
  });

  test("respects prefers-reduced-motion by disabling page transition animation", async ({ page }) => {
    // Emulate reduced motion
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/login");

    const main = page.locator(".page-transition main");
    await expect(main).toBeVisible();

    // In reduced-motion mode, animation should be 'none'
    const animationName = await main.evaluate((el) => {
      return window.getComputedStyle(el).animationName;
    });
    expect(animationName).toBe("none");
  });
});
