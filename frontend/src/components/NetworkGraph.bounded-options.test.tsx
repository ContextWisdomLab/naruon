/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const { apiGetMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
}));

const destroyMock = vi.fn();

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
    if (root) {
      act(() => root?.unmount());
    }
    root = null;
    container?.remove();
    container = null;
    vi.clearAllMocks();
  });

  it("instrumented iterable/Map fixture proves iteration stops early", async () => {
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

    const originalMapValues = Map.prototype.values;
    let edgeIterationCount = 0;
    let nodeIterationCount = 0;

    // Instrument Map.prototype.values to count iterations for our specific edges and nodes
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Map.prototype.values = function(this: Map<any, any>) {
      const iterator = originalMapValues.call(this);
      const isEdgeMap = this.has('edge-0');
      const isNodeMap = this.has('node-0');

      return {
        next: () => {
          if (isEdgeMap) edgeIterationCount++;
          if (isNodeMap) nodeIterationCount++;
          return iterator.next();
        },
        [Symbol.iterator]() { return this; }
      };
    } as any; // eslint-disable-line @typescript-eslint/no-explicit-any

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

      // Verify option caps still apply
      expect(relationshipSelect?.options.length).toBe(6); // 1 default + 5 options
      expect(nodeSelect?.options.length).toBe(9); // 1 default + 8 options

      // Verify the iteration count was strictly bounded and did not iterate all 50 items
      expect(edgeIterationCount).toBeLessThanOrEqual(15);
      expect(nodeIterationCount).toBeLessThanOrEqual(25);
    } finally {
      Map.prototype.values = originalMapValues;
      expect(Map.prototype.values).toBe(originalMapValues);
    }
  });
});
