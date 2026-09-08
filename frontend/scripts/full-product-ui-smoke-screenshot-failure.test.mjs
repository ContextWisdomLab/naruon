import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { FULL_PRODUCT_ROUTES, runRouteSmoke } from "./full-product-ui-smoke.mjs";

function createRoutePageThatCannotCaptureScreenshot() {
  let evaluationCount = 0;
  let screenshotAttempts = 0;
  let closed = false;

  return {
    page: {
      on: () => {},
      route: async () => {},
      goto: async () => {},
      waitForLoadState: async () => {},
      locator: () => ({ waitFor: async () => {}, innerText: async () => "Naruon" }),
      evaluate: async () => {
        evaluationCount += 1;
        if (evaluationCount === 1) return { duplicateIds: [], unnamedInteractive: [] };
        return { tagName: "BUTTON" };
      },
      keyboard: { press: async () => {} },
      waitForTimeout: async () => {},
      screenshot: async () => {
        screenshotAttempts += 1;
        throw new Error("screenshot-backend-unavailable");
      },
      close: async () => {
        closed = true;
      },
    },
    evidence: {
      get screenshotAttempts() {
        return screenshotAttempts;
      },
      get closed() {
        return closed;
      },
    },
  };
}

describe("full-product screenshot evidence", () => {
  it("fails the route after both screenshot attempts fail while still closing the page", async () => {
    const screenshotDirectory = await mkdtemp(path.join(tmpdir(), "naruon-full-product-smoke-failure-"));
    const { page, evidence } = createRoutePageThatCannotCaptureScreenshot();

    try {
      await expect(
        runRouteSmoke(
          { newPage: async () => page },
          FULL_PRODUCT_ROUTES[0],
          { name: "desktop", width: 1440, height: 1024 },
          1,
          screenshotDirectory,
        ),
      ).rejects.toThrow("screenshot-backend-unavailable");
      expect(evidence.screenshotAttempts).toBe(2);
      expect(evidence.closed).toBe(true);
    } finally {
      await rm(screenshotDirectory, { recursive: true, force: true });
    }
  });
});
