import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const workspaceManifest = readFileSync(
  fileURLToPath(new URL("../pnpm-workspace.yaml", import.meta.url)),
  "utf8",
);
const lockfile = readFileSync(
  fileURLToPath(new URL("../pnpm-lock.yaml", import.meta.url)),
  "utf8",
);

describe("frontend dependency lock security contract", () => {
  it("pins the patched js-yaml release in the workspace override and lock metadata", () => {
    expect(workspaceManifest).toMatch(/^\s{2}js-yaml:\s*"4\.3\.1"\s*$/m);
    expect(lockfile).toMatch(/^\s{2}js-yaml:\s*4\.3\.1\s*$/m);
  });

  it("contains no vulnerable js-yaml resolution and routes ESLint through 4.3.1", () => {
    const resolvedVersions = [...lockfile.matchAll(/^\s{2}js-yaml@(\d+\.\d+\.\d+):\s*$/gm)]
      .map((match) => match[1]);

    expect([...new Set(resolvedVersions)]).toEqual(["4.3.1"]);
    expect(lockfile).not.toMatch(/js-yaml@4\.3\.0|js-yaml:\s*4\.3\.0/);

    const snapshots = lockfile.slice(lockfile.indexOf("\nsnapshots:\n"));
    const eslintConfigSnapshot = snapshots.match(
      /^\s{2}'@eslint\/eslintrc@[^']+':\n((?:\s{4,}.*\n)+)/m,
    )?.[1];

    expect(eslintConfigSnapshot).toBeDefined();
    expect(eslintConfigSnapshot).toContain("js-yaml: 4.3.1");
  });
});
