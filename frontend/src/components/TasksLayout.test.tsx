/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("lucide-react", () => ({
  Plus: () => <svg aria-hidden="true" />,
  Search: () => <svg aria-hidden="true" />,
  Filter: () => <svg aria-hidden="true" />,
  User: () => <svg aria-hidden="true" />,
  CalendarDays: () => <svg aria-hidden="true" />,
  Inbox: () => <svg aria-hidden="true" />,
  AlertCircle: () => <svg aria-hidden="true" />,
  X: () => <svg aria-hidden="true" />,
}));

import { TasksLayout } from "./TasksLayout";

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

describe("TasksLayout", () => {
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
  });

  it("renders personal task rows as keyboard-native buttons that open details", async () => {
    const task = {
      id: "task-public-1",
      title: "거래처 회신 준비",
      status: "open",
      priority: "high",
      source_type: "email",
      source_email_id: "mail-public-1",
      related_thread_id: "thread-public-1",
      updated_at: "2026-06-18T05:00:00Z",
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/tasks")) return Promise.resolve(jsonResponse([task]));
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<TasksLayout />);
    });
    await flushAsyncWork();

    const myTasksTab = Array.from(container.querySelectorAll<HTMLButtonElement>("button"))
      .find((button) => button.textContent === "내 작업");

    act(() => {
      myTasksTab?.click();
    });

    const taskButton = Array.from(container.querySelectorAll<HTMLButtonElement>("button"))
      .find((button) => button.textContent?.includes("거래처 회신 준비"));

    expect(taskButton).not.toBeUndefined();
    expect(taskButton?.type).toBe("button");
    expect(taskButton?.className).toContain("focus-visible:ring-ring/40");

    act(() => {
      taskButton?.click();
    });

    expect(container.textContent).toContain("작업 설명");
    expect(container.textContent).toContain("관련 메일 열기");
    expect(container.textContent).toContain("거래처 회신 준비");
  });

  it("exposes the view mode toggle as a keyboard-navigable tablist", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/tasks")) return Promise.resolve(jsonResponse([]));
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<TasksLayout />);
    });
    await flushAsyncWork();

    const tablist = container.querySelector<HTMLElement>('[role="tablist"][aria-label="작업 보기 방식"]');
    expect(tablist).not.toBeNull();
    const tabs = Array.from(tablist?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? []);
    expect(tabs.map((tab) => tab.textContent)).toEqual(["내 작업", "위임한 작업", "칸반", "작업 상세"]);

    const kanbanTab = tabs.find((tab) => tab.textContent === "칸반");
    expect(kanbanTab?.getAttribute("aria-selected")).toBe("true");
    expect(kanbanTab?.tabIndex).toBe(0);
    for (const tab of tabs.filter((candidate) => candidate !== kanbanTab)) {
      expect(tab.getAttribute("aria-selected")).toBe("false");
      expect(tab.tabIndex).toBe(-1);
    }

    act(() => {
      kanbanTab?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    });
    await flushAsyncWork();

    const detailTab = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
      .find((tab) => tab.textContent === "작업 상세");
    expect(detailTab?.getAttribute("aria-selected")).toBe("true");
    expect(detailTab?.tabIndex).toBe(0);
  });
});
