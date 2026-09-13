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

  it("stops each option iterator at the configured limit without changing insertion order", async () => {
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

    const edgeIteratorReadCounts: number[] = [];
    const nodeIteratorReadCounts: number[] = [];

    // Count each populated graph-map iterator independently so rerenders cannot hide one unbounded iterator inside an aggregate total.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Map.prototype.values = function (this: Map<any, any>) {
      const iterator = originalMapValues.call(this);
      const readCounts = this.has("edge-0")
        ? edgeIteratorReadCounts
        : this.has("node-0")
          ? nodeIteratorReadCounts
          : null;
      const iteratorIndex = readCounts ? readCounts.push(0) - 1 : -1;

      return {
        next: () => {
          if (readCounts) readCounts[iteratorIndex] += 1;
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

      // for...of may read once beyond the accepted item before the body breaks: 5 relationships => at most 6 reads, 8 nodes => at most 9.
      expect(edgeIteratorReadCounts.length).toBeGreaterThan(0);
      expect(nodeIteratorReadCounts.length).toBeGreaterThan(0);
      expect(edgeIteratorReadCounts.every((count) => count <= 6)).toBe(true);
      expect(nodeIteratorReadCounts.every((count) => count <= 9)).toBe(true);
    } finally {
      Map.prototype.values = originalMapValues;
      expect(Map.prototype.values).toBe(originalMapValues);
    }
  });
});
