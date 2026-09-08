import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const networkGraphSource = readFileSync(
  fileURLToPath(new URL("./NetworkGraph.tsx", import.meta.url)),
  "utf8",
);

function sourceBetween(startMarker: string, endMarker: string): string {
  const startIndex = networkGraphSource.indexOf(startMarker);
  const endIndex = networkGraphSource.indexOf(endMarker, startIndex);

  expect(startIndex).toBeGreaterThanOrEqual(0);
  expect(endIndex).toBeGreaterThan(startIndex);

  return networkGraphSource.slice(startIndex, endIndex);
}

describe("NetworkGraph constant-time selection lookup contract", () => {
  it("keeps graph event selection on memoized maps without linear fallback scans", () => {
    const edgeSelection = sourceBetween("const selectEdge =", "const selectNode =");
    const nodeSelection = sourceBetween("const selectNode =", "const handleEdgeSelection =");

    expect(edgeSelection).toContain("edgeMap.get(String(edgeId))");
    expect(edgeSelection).not.toContain(".find(");

    expect(nodeSelection).toContain("nodeMap.get(String(nodeId))");
    expect(nodeSelection).toContain("?? String(nodeId)");
    expect(nodeSelection).not.toContain("findNodeLabel(");
    expect(nodeSelection).not.toContain(".find(");
  });

  it("keeps select controls on memoized maps without rescanning nodes or edges", () => {
    const graphNodeSelection = sourceBetween(
      "const selectGraphNode =",
      "const handleSelectFirstRelationship =",
    );
    const relationshipControl = sourceBetween(
      "const handleRelationshipOptionChange =",
      "const handleNodeOptionChange =",
    );
    const nodeControl = sourceBetween(
      "const handleNodeOptionChange =",
      "const handleZoomGraph =",
    );

    expect(graphNodeSelection).toContain("nodeMap.get(String(node.id))");
    expect(graphNodeSelection).toContain("?? String(node.id)");
    expect(graphNodeSelection).not.toContain("findNodeLabel(");
    expect(graphNodeSelection).not.toContain(".find(");

    expect(relationshipControl).toContain("edgeMap.get(value)");
    expect(relationshipControl).not.toContain(".find(");

    expect(nodeControl).toContain("nodeInstanceMap.get(value)");
    expect(nodeControl).not.toContain(".find(");
  });

  it("builds edge and node instance maps as first-wins lookups", () => {
    expect(networkGraphSource).toContain("firstGraphEntryById(edges");
    expect(networkGraphSource).toContain("firstGraphEntryById(nodes");
    expect(networkGraphSource).not.toMatch(/new Map\((edges|nodes)\.map\(/);
  });
});
