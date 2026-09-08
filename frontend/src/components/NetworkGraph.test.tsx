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

import { Network } from "vis-network";

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

describe("NetworkGraph", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;
  let resizeObserverCallback: ResizeObserverCallback | null = null;

  class MockResizeObserver {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();

    constructor(callback: ResizeObserverCallback) {
      resizeObserverCallback = callback;
    }
  }

  async function renderGraph() {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<NetworkGraph />);
    });
  }

  function getMountedContainer(): HTMLDivElement {
    if (!container) {
      throw new Error("NetworkGraph test container was not mounted.");
    }
    return container;
  }

  afterEach(() => {
    if (root) {
      act(() => root?.unmount());
    }
    root = null;
    container?.remove();
    container = null;
    resizeObserverCallback = null;
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("announces an empty graph as a polite status region", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [],
          edges: [],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const status = container?.querySelector('[role="status"][aria-live="polite"]');
    expect(status?.textContent).toContain("관계 데이터가 없습니다");
    expect(Network).not.toHaveBeenCalled();
  });

  it("describes the unavailable first-relationship action programmatically", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [{ id: "node-1", label: "노드" }],
          edges: [],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const mountedContainer = getMountedContainer();
    const wrapper = mountedContainer.querySelector('span[tabindex="0"]');
    const button = mountedContainer.querySelector('button[disabled]');
    const descriptionId = wrapper?.getAttribute("aria-describedby");

    expect(wrapper).toBeInstanceOf(HTMLSpanElement);
    expect(wrapper?.className).toContain("cursor-not-allowed");
    expect(wrapper?.getAttribute("title")).toBe("표시할 관계 데이터가 없습니다.");
    expect(wrapper?.className).toContain("focus-visible:ring-2");
    expect(descriptionId).toBeTruthy();
    expect(document.getElementById(descriptionId ?? "")?.textContent).toBe(
      "표시할 관계 데이터가 없습니다.",
    );
    expect(button).toBeInstanceOf(HTMLButtonElement);
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button?.className).toContain("disabled:cursor-not-allowed");
    expect(button?.className).toContain("pointer-events-none");
  });

  it("announces graph loading failures as a polite alert", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.fn(() => Promise.reject(new Error("network unavailable")));
    vi.stubGlobal("fetch", fetchMock);

    try {
      await renderGraph();
      await flushAsyncWork();

      const alert = container?.querySelector('[role="alert"][aria-live="polite"]');
      expect(alert?.textContent).toContain("관계 맥락을 불러오지 못했습니다");
      expect(Network).not.toHaveBeenCalled();
    } finally {
      consoleError.mockRestore();
    }
  });

  it("coerces graph tooltip titles to text-only DOM nodes before vis-network renders them", async () => {
    const maliciousTitle = '<img src=x onerror="globalThis.__xss = true">';
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [{ id: "n1", label: "Node", title: maliciousTitle }],
          edges: [{ from: "n1", to: "n1", title: maliciousTitle }],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    expect(Network).toHaveBeenCalledTimes(1);
    const networkData = vi.mocked(Network).mock.calls[0]?.[1];
    const nodes = Array.isArray(networkData?.nodes) ? networkData.nodes : [];
    const edges = Array.isArray(networkData?.edges) ? networkData.edges : [];
    const nodeTitle = nodes[0]?.title;
    const edgeTitle = edges[0]?.title;

    expect(nodeTitle).toBeInstanceOf(HTMLElement);
    expect(edgeTitle).toBeInstanceOf(HTMLElement);
    expect((nodeTitle as HTMLElement).textContent).toBe(maliciousTitle);
    expect((edgeTitle as HTMLElement).textContent).toBe(maliciousTitle);
    expect((nodeTitle as HTMLElement).innerHTML).not.toContain("<img");
    expect((edgeTitle as HTMLElement).innerHTML).not.toContain("<img");
  });

  it("escapes graph labels before passing them to vis-network while keeping React text plain", async () => {
    const maliciousLabel = '<img src=x onerror="globalThis.__xss = true">';
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [{ id: "n1", label: maliciousLabel, title: "Node" }],
          edges: [{ from: "n1", to: "n1" }],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const mountedContainer = getMountedContainer();
    expect(Network).toHaveBeenCalledTimes(1);
    const networkData = vi.mocked(Network).mock.calls[0]?.[1];
    const nodes = Array.isArray(networkData?.nodes) ? networkData.nodes : [];

    expect(nodes[0]?.label).toBe("&lt;img src=x onerror=&quot;globalThis.__xss = true&quot;&gt;");
    expect(nodes[0]?.label).not.toContain("<img");
    expect(mountedContainer.textContent).toContain(maliciousLabel);
    expect(mountedContainer.innerHTML).not.toContain("<img");
  });

  it("renders a Korean text fallback for graph relationships", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [{ id: "person-1", label: "김지현", title: "PM" }],
          edges: [{ source: "person-1", target: "person-1", title: "관련 메일" }],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const mountedContainer = getMountedContainer();
    expect(mountedContainer.textContent).toContain("관계 이해");
    expect(mountedContainer.textContent).toContain("1개 노드");
    expect(mountedContainer.textContent).toContain("1개 관계");
    expect(mountedContainer.textContent).toContain("김지현");
    expect(mountedContainer.textContent).not.toContain("nodes and");
  });

  it("exposes accessible relationship detail and zoom controls for the graph", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [
            { id: "sender-1", label: "김지현", title: "PM" },
            { id: "recipient-1", label: "사용자", title: "Owner" },
            { id: "calendar-1", label: "일정", title: "Schedule" },
          ],
          edges: [
            { source: "sender-1", target: "recipient-1", title: "메일 2건" },
            { source: "recipient-1", target: "calendar-1", title: "일정 후보 1건" },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const mountedContainer = getMountedContainer();
    const buttons = Array.from(mountedContainer.querySelectorAll("button"));
    const relationshipButton = buttons.find((button) => button.textContent === "첫 관계 보기");
    const zoomButton = buttons.find((button) => button.textContent === "그래프 확대");
    const fitButton = buttons.find((button) => button.textContent === "전체 그래프 맞춤");

    expect(relationshipButton).toBeInstanceOf(HTMLButtonElement);
    expect(zoomButton).toBeInstanceOf(HTMLButtonElement);
    expect(fitButton).toBeInstanceOf(HTMLButtonElement);

    await act(async () => {
      relationshipButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(selectEdgesMock).toHaveBeenCalledWith(["relationship-0-sender-1-recipient-1"]);
    expect(fitMock).toHaveBeenCalledWith({
      nodes: ["sender-1", "recipient-1"],
      animation: false,
    });
    expect(mountedContainer.textContent).toContain("선택된 관계: 김지현 -> 사용자 (메일 2건)");
    expect(mountedContainer.textContent).toContain("첫 관계를 선택했습니다.");

    const relationshipSelect = mountedContainer.querySelector('select[aria-label="관계 선택"]');
    expect(relationshipSelect).toBeInstanceOf(HTMLSelectElement);

    await act(async () => {
      if (relationshipSelect instanceof HTMLSelectElement) {
        relationshipSelect.value = "relationship-1-recipient-1-calendar-1";
        relationshipSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });

    expect(selectEdgesMock).toHaveBeenCalledWith(["relationship-1-recipient-1-calendar-1"]);
    expect(mountedContainer.textContent).toContain("선택된 관계: 사용자 -> 일정 (일정 후보 1건)");
    expect(mountedContainer.textContent).toContain("선택한 관계를 열었습니다.");

    const nodeSelect = mountedContainer.querySelector('select[aria-label="노드 선택"]');
    expect(nodeSelect).toBeInstanceOf(HTMLSelectElement);

    await act(async () => {
      if (nodeSelect instanceof HTMLSelectElement) {
        nodeSelect.value = "calendar-1";
        nodeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });

    expect(selectNodesMock).toHaveBeenCalledWith(["calendar-1"]);
    expect(fitMock).toHaveBeenLastCalledWith({ nodes: ["calendar-1"], animation: false });
    expect(mountedContainer.textContent).toContain("선택된 노드: 일정");
    expect(mountedContainer.textContent).toContain("선택한 노드를 열었습니다.");

    await act(async () => {
      zoomButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(moveToMock).toHaveBeenCalledWith({ scale: 1.15, animation: false });
    expect(mountedContainer.textContent).toContain("그래프 확대 완료");

    await act(async () => {
      fitButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(fitMock).toHaveBeenLastCalledWith({ animation: false });
    expect(mountedContainer.textContent).toContain("그래프 맞춤 완료");
  });

  function registeredGraphHandler(eventName: string) {
    const handler = onMock.mock.calls.find((call) => call[0] === eventName)?.[1];
    if (typeof handler !== "function") {
      throw new Error(`${eventName} handler was not registered.`);
    }
    return handler as (event: {
      nodes?: Array<number | string>;
      edges?: Array<number | string>;
    }) => void;
  }

  it("resolves vis-network selection events for mixed numeric and string ids", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [
            { id: 101, label: "발신자", title: "PM" },
            { id: "recipient-1", label: "수신자", title: "Owner" },
          ],
          edges: [
            { id: 7, from: 101, to: "recipient-1", title: "메일 1건" },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const mountedContainer = getMountedContainer();
    const selectNode = registeredGraphHandler("selectNode");
    const selectEdge = registeredGraphHandler("selectEdge");

    await act(async () => {
      selectNode({ nodes: [101] });
    });

    const nodeSelect = mountedContainer.querySelector('select[aria-label="노드 선택"]');
    expect(nodeSelect).toBeInstanceOf(HTMLSelectElement);
    expect((nodeSelect as HTMLSelectElement).value).toBe("101");
    expect(mountedContainer.textContent).toContain("선택된 노드: 발신자");
    expect(mountedContainer.textContent).toContain("그래프에서 노드를 선택했습니다.");

    await act(async () => {
      selectEdge({ edges: [7] });
    });

    const relationshipSelect = mountedContainer.querySelector('select[aria-label="관계 선택"]');
    expect(relationshipSelect).toBeInstanceOf(HTMLSelectElement);
    expect((relationshipSelect as HTMLSelectElement).value).toBe("7");
    expect(mountedContainer.textContent).toContain("선택된 관계: 발신자 -> 수신자 (메일 1건)");
    expect(mountedContainer.textContent).toContain("그래프에서 관계를 선택했습니다.");
  });

  it("keeps the first edge instance when duplicate relationship ids collide", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [
            { id: "sender-1", label: "김지현", title: "PM" },
            { id: "recipient-1", label: "사용자", title: "Owner" },
            { id: "calendar-1", label: "일정", title: "Schedule" },
          ],
          edges: [
            { id: "rel-shared", from: "sender-1", to: "recipient-1", title: "메일 2건" },
            { id: "rel-shared", from: "sender-1", to: "calendar-1", title: "일정 후보 1건" },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const mountedContainer = getMountedContainer();
    const selectEdge = registeredGraphHandler("selectEdge");

    await act(async () => {
      selectEdge({ edges: ["rel-shared"] });
    });

    expect(mountedContainer.textContent).toContain("선택된 관계: 김지현 -> 사용자 (메일 2건)");
    expect(mountedContainer.textContent).not.toContain("선택된 관계: 김지현 -> 일정 (일정 후보 1건)");
    expect(selectEdgesMock).not.toHaveBeenCalled();

    const relationshipSelect = mountedContainer.querySelector('select[aria-label="관계 선택"]');
    expect(relationshipSelect).toBeInstanceOf(HTMLSelectElement);

    await act(async () => {
      if (relationshipSelect instanceof HTMLSelectElement) {
        relationshipSelect.value = "rel-shared";
        relationshipSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });

    expect(selectEdgesMock).toHaveBeenCalledWith(["rel-shared"]);
    expect(fitMock).toHaveBeenCalledWith({
      nodes: ["sender-1", "recipient-1"],
      animation: false,
    });
    expect(fitMock).not.toHaveBeenCalledWith({
      nodes: ["sender-1", "calendar-1"],
      animation: false,
    });
    expect(mountedContainer.textContent).toContain("선택된 관계: 김지현 -> 사용자 (메일 2건)");
    expect(mountedContainer.textContent).toContain("선택한 관계를 열었습니다.");
  });

  it("normalizes backend source target edges before rendering the graph", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [
            { id: "sender-1", label: "김지현", title: "PM" },
            { id: "recipient-1", label: "사용자", title: "Owner" },
          ],
          edges: [{ source: "sender-1", target: "recipient-1", weight: 2, title: "메일 2건" }],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    expect(Network).toHaveBeenCalledTimes(1);
    const networkData = vi.mocked(Network).mock.calls[0]?.[1];
    const edges = Array.isArray(networkData?.edges) ? networkData.edges : [];
    expect(edges[0]).toMatchObject({
      from: "sender-1",
      id: "relationship-0-sender-1-recipient-1",
      to: "recipient-1",
      weight: 2,
    });
    expect(edges[0]).not.toHaveProperty("source");
    expect(edges[0]).not.toHaveProperty("target");
  });

  it("does not expose graph records without an id as selectable nodes", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [
            { id: null, label: "식별자 없는 노드" },
            { id: "person-1", label: "김지현" },
          ],
          edges: [{ from: "person-1", to: "person-1", title: "관련 메일" }],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const nodeSelect = getMountedContainer().querySelector(
      'select[aria-label="노드 선택"]',
    );
    expect(nodeSelect).toBeInstanceOf(HTMLSelectElement);
    expect(nodeSelect?.textContent).toContain("김지현");
    expect(nodeSelect?.textContent).not.toContain("식별자 없는 노드");
  });

  it("keeps raw endpoint ids visible when a relationship has no matching node", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [{ id: "known-node", label: "확인된 노드" }],
          edges: [{ from: "missing-from", to: "missing-to", title: "고립 관계" }],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await renderGraph();
    await flushAsyncWork();

    const mountedContainer = getMountedContainer();
    expect(mountedContainer.textContent).toContain(
      "관계 1: missing-from -> missing-to (고립 관계)",
    );

    const relationshipButton = Array.from(mountedContainer.querySelectorAll("button")).find(
      (button) => button.textContent === "첫 관계 보기",
    );
    await act(async () => {
      relationshipButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(mountedContainer.textContent).toContain(
      "선택된 관계: missing-from -> missing-to (고립 관계)",
    );
  });

  it("refits the graph when the viewport changes", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          nodes: [{ id: "person-1", label: "김지현", title: "PM" }],
          edges: [{ from: "person-1", to: "person-1", title: "관련 메일" }],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("ResizeObserver", MockResizeObserver);

    await renderGraph();
    await flushAsyncWork();

    expect(Network).toHaveBeenCalledTimes(1);
    expect(resizeObserverCallback).not.toBeNull();
    expect(fitMock).toHaveBeenCalledTimes(0);

    vi.useFakeTimers();
    try {
      await act(async () => {
        resizeObserverCallback?.([] as ResizeObserverEntry[], {} as ResizeObserver);
        resizeObserverCallback?.([] as ResizeObserverEntry[], {} as ResizeObserver);
        vi.advanceTimersByTime(49);
      });

      expect(fitMock).toHaveBeenCalledTimes(0);

      await act(async () => {
        vi.advanceTimersByTime(1);
      });

      expect(fitMock).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
