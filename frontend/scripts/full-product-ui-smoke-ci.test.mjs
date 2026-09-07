import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appCiWorkflowPath = path.resolve(frontendDir, "..", ".github", "workflows", "app-ci.yml");

describe("full product responsive evidence in Application CI", () => {
  it("runs the full-product smoke across every approved viewport", async () => {
    const workflow = await readFile(appCiWorkflowPath, "utf-8");

    expect(workflow).toContain('NARUON_FULL_PRODUCT_VIEWPORTS: "all"');
  });
});
