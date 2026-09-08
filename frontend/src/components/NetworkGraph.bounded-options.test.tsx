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

  it("materializes only the first five relationships and first eight nodes", async () => {
    const nodes = Array.from({ length: 12 }, (_, index) => ({
      id: `node-${index}`,
      label: `노드 ${index}`,
    }));
    const edges = Array.from({ length: 10 }, (_, index) => ({
      id: `edge-${index}`,
      from: `node-${index}`,
      to: `node-${index + 1}`,
      title: `관계 ${index}`,
    }));

    apiGetMock.mockResolvedValue({ nodes, edges });

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

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
    expect(container.textContent).not.toContain("노드 8");
    expect(container.textContent).not.toContain("관계 6:");
  });
});
