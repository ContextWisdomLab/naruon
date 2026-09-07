import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appCiWorkflowPath = path.resolve(frontendDir, "..", ".github", "workflows", "app-ci.yml");

describe("full product responsive evidence in Application CI", () => {
  it("runs every approved viewport and preserves the screenshots", async () => {
    const workflow = await readFile(appCiWorkflowPath, "utf-8");

    expect(workflow).toContain('NARUON_FULL_PRODUCT_VIEWPORTS: "all"');
    expect(workflow).toContain(
      "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
    );
    expect(workflow).toContain("/tmp/naruon-full-product-smoke-*/*.png");
    expect(workflow).toContain("if-no-files-found: error");
  });
});
