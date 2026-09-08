/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const { apiGetMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
}));

const destroyMock = vi.fn();
const originalMapValues = Map.prototype.values;

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: apiGetMock,
  },
}));

vi.mock("vis-network", () => ({
  Network: vi.fn(function MockNetwork() {
    return {
      destroy: destroyMock,
      fit: vi.fn(),
      moveTo: vi.fn(),
      off: vi.fn(),
      on: vi.fn(),
      selectEdges: vi.fn(),
      selectNodes: vi.fn(),
    };
  }),
}));

import NetworkGraph from "./NetworkGraph";

async function flushAsyncWork() {
  for (let index = 0; index < 5; index += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

describe("NetworkGraph bounded option materialization", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    // Keep the process-global Map prototype clean even if setup or an assertion fails before the local finally block.
    Map.prototype.values = originalMapValues;
    if (root) {
      act(() => root?.unmount());
    }
    root = null;
    container?.remove();
    container = null;
    vi.clearAllMocks();
  });

  it("stops option iteration at the configured limits without changing insertion order", async () => {
    const nodes = Array.from({ length: 50 }, (_, index) => ({
      id: `node-${index}`,
      label: `노드 ${index}`,
    }));
    const edges = Array.from({ length: 50 }, (_, index) => ({
      id: `edge-${index}`,
      from: `node-${index}`,
      to: `node-${index + 1}`,
      title: `관계 ${index}`,
    }));

    apiGetMock.mockResolvedValue({ nodes, edges });

    let edgeIterationCount = 0;
    let nodeIterationCount = 0;

    // Count only the populated graph maps so unrelated framework Maps cannot affect the bound.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Map.prototype.values = function (this: Map<any, any>) {
      const iterator = originalMapValues.call(this);
      const isEdgeMap = this.has("edge-0");
      const isNodeMap = this.has("node-0");

      return {
        next: () => {
          if (isEdgeMap) edgeIterationCount += 1;
          if (isNodeMap) nodeIterationCount += 1;
          return iterator.next();
        },
        [Symbol.iterator]() {
          return this;
        },
      };
    } as typeof Map.prototype.values;

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    try {
      await act(async () => {
        root?.render(<NetworkGraph />);
      });
      await flushAsyncWork();

      const relationshipSelect = container.querySelector(
        'select[aria-label="관계 선택"]',
      ) as HTMLSelectElement | null;
      const nodeSelect = container.querySelector(
        'select[aria-label="노드 선택"]',
      ) as HTMLSelectElement | null;

      expect(relationshipSelect).toBeInstanceOf(HTMLSelectElement);
      expect(nodeSelect).toBeInstanceOf(HTMLSelectElement);
      expect(Array.from(relationshipSelect?.options ?? []).map((option) => option.value)).toEqual([
        "",
        "edge-0",
        "edge-1",
        "edge-2",
        "edge-3",
        "edge-4",
      ]);
      expect(Array.from(nodeSelect?.options ?? []).map((option) => option.value)).toEqual([
        "",
        "node-0",
        "node-1",
        "node-2",
        "node-3",
        "node-4",
        "node-5",
        "node-6",
        "node-7",
      ]);

      // A sixth/ninth iterator read can occur because for...of retrieves the next item before the body breaks.
      expect(edgeIterationCount).toBeLessThanOrEqual(15);
      expect(nodeIterationCount).toBeLessThanOrEqual(25);
    } finally {
      Map.prototype.values = originalMapValues;
      expect(Map.prototype.values).toBe(originalMapValues);
    }
  });
});
