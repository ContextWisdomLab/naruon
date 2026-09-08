import { describe, expect, it } from "vitest";
import { rm, stat } from "node:fs/promises";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  FULL_PRODUCT_ACCESSIBILITY_CHECK_NAMES,
  FULL_PRODUCT_CRITICAL_INTERACTION_ROUTE_NAMES,
  FULL_PRODUCT_CRITICAL_INTERACTION_VIEWPORT_NAMES,
  FULL_PRODUCT_DESKTOP_INTERACTION_ROUTE_NAMES,
  FULL_PRODUCT_ROUTES,
  createFullProductArtifactDirectory,
  createFullProductServerLaunchSpec,
  fullProductScreenshotName,
  isTcpPortOpen,
  resolveFullProductArtifactPath,
  resolveFullProductBaseUrl,
  resolveFullProductChromePath,
  resolveFullProductScreenshotProfile,
  resolveFullProductViewportSpecs,
  runRouteSmoke,
} from "./full-product-ui-smoke.mjs";

describe("route smoke late browser errors", () => {
  it.each(["console", "pageerror"])("rejects %s errors emitted during capture", async (eventName) => {
    const handlers = {};
    let evaluationCount = 0;
    const page = {
      on: (name, handler) => { handlers[name] = handler; },
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
      screenshot: async () => {
        if (eventName === "console") {
          handlers.console({ type: () => "error", text: () => "late-browser-failure" });
        } else {
          handlers.pageerror(new Error("late-browser-failure"));
        }
      },
      close: async () => {},
    };
    await expect(runRouteSmoke(
      { newPage: async () => page },
      FULL_PRODUCT_ROUTES[0],
      { name: "desktop", width: 1440, height: 1024 },
      1,
      path.join(tmpdir(), "naruon-full-product-smoke-unit"),
    )).rejects.toThrow("late-browser-failure");
  });
});

describe("full product UI smoke base URL guard", () => {
  it("allows localhost full-product smoke targets", () => {
    expect(resolveFullProductBaseUrl("http://127.0.0.1:3001").hostname).toBe("127.0.0.1");
    expect(resolveFullProductBaseUrl("http://localhost:3001").hostname).toBe("localhost");
    expect(resolveFullProductBaseUrl("http://[::1]:3001").hostname).toBe("[::1]");
  });

  it("rejects non-localhost targets", () => {
    expect(() => resolveFullProductBaseUrl("https://staging.example.com")).toThrow("localhost targets");
    expect(() => resolveFullProductBaseUrl("https://naruon.example.com")).toThrow("localhost targets");
    expect(() => resolveFullProductBaseUrl("http://192.168.0.10:3000")).toThrow("localhost targets");
    expect(() => resolveFullProductBaseUrl("http://127.0.0.1:3000")).toThrow("localhost targets");
    expect(() => resolveFullProductBaseUrl("https://127.0.0.1:3001")).toThrow("localhost targets");
    expect(() => resolveFullProductBaseUrl("http://127.0.0.1:3001/admin")).toThrow("localhost targets");
    expect(() => resolveFullProductBaseUrl("http://127.0.0.1:3001?target=internal")).toThrow("localhost targets");
    expect(() => resolveFullProductBaseUrl("http://user@127.0.0.1:3001")).toThrow("localhost targets");
    expect(() => resolveFullProductBaseUrl("http://2130706433:3001")).toThrow("localhost targets");
  });

  it("creates private unique artifact directories and contains screenshot paths", async () => {
    const firstDirectory = await createFullProductArtifactDirectory("/tmp/naruon-full-product-smoke");
    const secondDirectory = await createFullProductArtifactDirectory("/tmp/naruon-full-product-smoke");
    try {
      const firstRelativePath = path.relative(tmpdir(), firstDirectory);
      expect(firstRelativePath).not.toMatch(/^\.\.(?:[/\\]|$)/u);
      expect(path.isAbsolute(firstRelativePath)).toBe(false);
      expect(firstDirectory).not.toBe(secondDirectory);
      expect((await stat(firstDirectory)).mode & 0o077).toBe(0);
      expect(resolveFullProductArtifactPath(firstDirectory, "desktop-home.png")).toBe(
        path.join(firstDirectory, "desktop-home.png"),
      );
      expect(() => resolveFullProductArtifactPath(firstDirectory, "../escape.png")).toThrow("safe file name");
      expect(() => resolveFullProductArtifactPath(firstDirectory, "nested/escape.png")).toThrow("safe file name");
      await expect(createFullProductArtifactDirectory("/tmp/../etc")).rejects.toThrow("approved artifact profile");
    } finally {
      await rm(firstDirectory, { recursive: true, force: true });
      await rm(secondDirectory, { recursive: true, force: true });
    }
  });

  it("prefers the screenshot profile variable and preserves the legacy directory alias", () => {
    expect(
      resolveFullProductScreenshotProfile({
        NARUON_FULL_PRODUCT_SCREENSHOT_PROFILE:
          "/tmp/naruon-full-product-responsive-qa",
        NARUON_FULL_PRODUCT_SCREENSHOT_DIR:
          "/tmp/naruon-full-product-smoke",
      }),
    ).toBe("/tmp/naruon-full-product-responsive-qa");
    expect(
      resolveFullProductScreenshotProfile({
        NARUON_FULL_PRODUCT_SCREENSHOT_DIR:
          "/tmp/naruon-full-product-smoke",
      }),
    ).toBe("/tmp/naruon-full-product-smoke");
  });

  it("allows only fixed system Chrome fallback executables", () => {
    expect(resolveFullProductChromePath("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")).toBe(
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    );
    expect(resolveFullProductChromePath("/usr/bin/google-chrome")).toBe("/usr/bin/google-chrome");
    expect(() => resolveFullProductChromePath("/tmp/attacker-controlled-chrome")).toThrow("approved Chrome executable");
    expect(() => resolveFullProductChromePath("../../bin/chrome")).toThrow("approved Chrome executable");
  });

  it("launches Next through the current Node executable with fixed argv", () => {
    const launchSpec = createFullProductServerLaunchSpec("http://127.0.0.1:3001");
    expect(launchSpec.executable).toBe(process.execPath);
    expect(launchSpec.args.slice(-6)).toEqual([
      "dev",
      "--webpack",
      "--hostname",
      "127.0.0.1",
      "--port",
      "3001",
    ]);
    expect(() => createFullProductServerLaunchSpec("http://127.0.0.1:3001;touch /tmp/pwned")).toThrow(
      "localhost targets",
    );
  });

  it("covers the ten buyer-review IA routes", () => {
    expect(FULL_PRODUCT_ROUTES.map((route) => route.path)).toEqual([
      "/",
      "/mail",
      "/search",
      "/calendar",
      "/tasks",
      "/projects",
      "/data",
      "/ai-hub",
      "/security",
      "/settings",
    ]);
  });

  it("resolves desktop and mobile responsive capture viewports", () => {
    expect(resolveFullProductViewportSpecs("desktop,mobile").map((viewport) => viewport.name)).toEqual([
      "desktop",
      "mobile",
    ]);
    expect(resolveFullProductViewportSpecs("all").map((viewport) => viewport.name)).toEqual(["desktop", "mobile"]);
    expect(() => resolveFullProductViewportSpecs("tablet")).toThrow("Unknown full-product viewport");
    expect(() => resolveFullProductViewportSpecs("desktop,desktop")).toThrow("Duplicate full-product viewport");
  });

  it("keeps the legacy desktop screenshot names unless multiple viewports are captured", () => {
    const [homeRoute] = FULL_PRODUCT_ROUTES;
    const [desktopViewport, mobileViewport] = resolveFullProductViewportSpecs("desktop,mobile");
    expect(fullProductScreenshotName(homeRoute, desktopViewport, 1)).toBe("home.png");
    expect(fullProductScreenshotName(homeRoute, desktopViewport, 2)).toBe("desktop-home.png");
    expect(fullProductScreenshotName(homeRoute, mobileViewport, 2)).toBe("mobile-home.png");
  });

  it("tracks only buyer-critical interaction routes with existing smoke route names", () => {
    const routeNames = new Set(FULL_PRODUCT_ROUTES.map((route) => route.name));
    expect(FULL_PRODUCT_CRITICAL_INTERACTION_ROUTE_NAMES).toEqual([
      "mail",
      "search",
      "calendar",
      "tasks",
      "projects",
      "data",
      "ai-hub",
      "security",
      "settings",
    ]);
    expect(FULL_PRODUCT_CRITICAL_INTERACTION_VIEWPORT_NAMES).toEqual(["desktop", "mobile"]);
    expect(FULL_PRODUCT_CRITICAL_INTERACTION_ROUTE_NAMES.every((routeName) => routeNames.has(routeName))).toBe(true);
    expect(FULL_PRODUCT_DESKTOP_INTERACTION_ROUTE_NAMES).toEqual(FULL_PRODUCT_CRITICAL_INTERACTION_ROUTE_NAMES);
  });

  it("keeps the full-product accessibility smoke scoped to basic automatable checks", () => {
    expect(FULL_PRODUCT_ACCESSIBILITY_CHECK_NAMES).toEqual([
      "visible-duplicate-id",
      "visible-interactive-accessible-name",
      "keyboard-tab-focus-entry",
    ]);
  });

  it("detects an existing local TCP listener before spawning another dev server", async () => {
    const server = net.createServer();
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

    try {
      const address = server.address();
      expect(address).not.toBeNull();
      expect(typeof address).not.toBe("string");
      await expect(isTcpPortOpen(new URL(`http://127.0.0.1:${address.port}`))).resolves.toBe(true);
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
  });
});
