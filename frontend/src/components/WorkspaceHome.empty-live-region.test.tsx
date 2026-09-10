/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/EmailList", () => ({
  EmailList: () => <section aria-label="mock email list">mock email list</section>,
}));

vi.mock("@/components/EmailDetail", () => ({
  EmailDetail: () => <section aria-label="mock email detail">mock email detail</section>,
}));

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}));

vi.mock("@/components/mobile-workspace-panels", () => ({
  MobileCalendarPanel: () => <section>mock calendar</section>,
  MobileSearchPanel: () => <section>mock search</section>,
}));

vi.mock("next/dynamic", () => ({
  default: () => function MockDynamic() {
    return <div>mock graph</div>;
  },
}));

vi.mock("lucide-react", () => ({
  CalendarDays: () => <svg aria-hidden="true" />,
  CheckCircle2: () => <svg aria-hidden="true" />,
  Inbox: () => <svg aria-hidden="true" />,
  Network: () => <svg aria-hidden="true" />,
  Send: () => <svg aria-hidden="true" />,
  Settings: () => <svg aria-hidden="true" />,
  Sparkles: () => <svg aria-hidden="true" />,
}));

import { WorkspaceHome } from "./WorkspaceHome";

type DeferredResponse = {
  promise: Promise<{ ok: true; json: () => Promise<unknown> }>;
  resolve: (body: unknown) => void;
};

function deferredResponse(): DeferredResponse {
  let resolvePromise!: (response: { ok: true; json: () => Promise<unknown> }) => void;
  const promise = new Promise<{ ok: true; json: () => Promise<unknown> }>((resolve) => {
    resolvePromise = resolve;
  });
  return {
    promise,
    resolve: (body: unknown) => resolvePromise({ ok: true, json: async () => body }),
  };
}

async function waitForCondition(condition: () => boolean) {
  for (let index = 0; index < 20; index += 1) {
    if (condition()) return;
    await act(async () => {
      await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
  throw new Error("waitForCondition timed out after 20 attempts");
}

function statusWithText(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll<HTMLElement>('[role="status"]')).find(
    (element) => element.textContent?.includes(text),
  ) ?? null;
}

describe("WorkspaceHome empty-state live regions", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    root = null;
    container?.remove();
    container = null;
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("announces primary dashboard empty states after asynchronous loading completes", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));

    const emailsResponse = deferredResponse();
    const pendingRepliesResponse = deferredResponse();
    const tasksResponse = deferredResponse();

    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/emails/pending-replies?limit=3")) return pendingRepliesResponse.promise;
      if (url.endsWith("/api/emails")) return emailsResponse.promise;
      if (url.endsWith("/api/tasks")) return tasksResponse.promise;
      if (url.endsWith("/api/calendar/writeback-sources") || url.endsWith("/api/webdav/folders")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.endsWith("/api/search")) {
        return Promise.resolve({ ok: true, json: async () => ({ results: [] }) });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });

    expect(container.textContent).toContain("답변 대기 메일을 불러오는 중...");
    expect(container.textContent).toContain("작업을 불러오는 중...");
    expect(container.textContent).toContain("메일을 불러오는 중...");

    await act(async () => {
      emailsResponse.resolve({ emails: [] });
      pendingRepliesResponse.resolve({ emails: [] });
      tasksResponse.resolve([]);
    });
    await waitForCondition(() => container?.textContent?.includes("수신된 메일이 없습니다.") ?? false);

    for (const copy of [
      "답변 대기 중인 보낸 메일이 없습니다.",
      "대기 작업이 없습니다.",
      "수신된 메일이 없습니다.",
    ]) {
      const emptyStatus = statusWithText(container, copy);
      expect(emptyStatus, copy).not.toBeNull();
      expect(emptyStatus?.getAttribute("aria-live"), copy).toBe("polite");
    }

    expect(container.textContent).not.toContain("답변 대기 메일을 불러오는 중...");
    expect(container.textContent).not.toContain("작업을 불러오는 중...");
    expect(container.textContent).not.toContain("메일을 불러오는 중...");
  });
});