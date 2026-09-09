import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

function nodeLabelMemoSource(): string {
  const source = readFileSync(new URL("./NetworkGraph.tsx", import.meta.url), "utf8");
  const start = source.indexOf("  const nodeLabels = useMemo(() => {");
  const end = source.indexOf("  const firstEdge =", start);

  expect(start).toBeGreaterThanOrEqual(0);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe("NetworkGraph bounded label summary", () => {
  it("caps label-summary work at five accepted labels without whole-array transforms", () => {
    const memoSource = nodeLabelMemoSource();

    expect(memoSource).toContain("for (const node of nodes)");
    expect(memoSource).toContain("if (labels.length >= 5) break;");
    expect(memoSource).not.toContain(".map(");
    expect(memoSource).not.toContain(".filter(");
    expect(memoSource).not.toContain(".slice(");
  });
});
