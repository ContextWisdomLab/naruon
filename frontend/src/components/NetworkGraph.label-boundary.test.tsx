/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const destroyMock = vi.fn();
const fitMock = vi.fn();
const moveToMock = vi.fn();
const offMock = vi.fn();
const onMock = vi.fn();
const selectEdgesMock = vi.fn();
const selectNodesMock = vi.fn();

vi.mock("vis-network", () => ({
  Network: vi.fn(function MockNetwork() {
    return {
      destroy: destroyMock,
      fit: fitMock,
      moveTo: moveToMock,
      off: offMock,
      on: onMock,
      selectEdges: selectEdgesMock,
      selectNodes: selectNodesMock,
    };
  }),
}));

import NetworkGraph from "./NetworkGraph";

function jsonResponse(body: unknown) {
  return {
    ok: true,
    json: async () => body,
  };
}

async function flushAsyncWork() {
  for (let index = 0; index < 5; index += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

describe("NetworkGraph label boundary", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) {
      act(() => root?.unmount());
    }
    root = null;
    container?.remove();
    container = null;
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("renders only the first five non-empty related-node labels in source order", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [
            { id: "node-a", label: "A" },
            { id: "empty-1", label: "" },
            { id: "node-b", label: "B" },
            { id: "node-c", label: "C" },
            { id: "empty-2", label: "" },
            { id: "node-d", label: "D" },
            { id: "node-e", label: "E" },
            { id: "node-f", label: "F" },
          ],
          edges: [],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<NetworkGraph />);
    });
    await flushAsyncWork();

    const summary = Array.from(container.querySelectorAll("p")).find((element) =>
      element.textContent?.includes("관련 노드:"),
    );

    expect(summary?.textContent?.replace(/\s+/g, " ").trim()).toBe(
      "관련 노드: A, B, C, D, E",
    );
    expect(summary?.textContent).not.toContain("F");
  });
});
