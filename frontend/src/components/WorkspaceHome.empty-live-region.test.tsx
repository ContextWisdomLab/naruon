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
  bodyPromise: Promise<unknown>;
  resolveResponse: () => void;
  resolveBody: (body: unknown) => void;
};

function deferredResponse(): DeferredResponse {
  let resolveResponsePromise!: (response: { ok: true; json: () => Promise<unknown> }) => void;
  let resolveBodyPromise!: (body: unknown) => void;
  const bodyPromise = new Promise<unknown>((resolve) => {
    resolveBodyPromise = resolve;
  });
  const promise = new Promise<{ ok: true; json: () => Promise<unknown> }>((resolve) => {
    resolveResponsePromise = resolve;
  });
  const response = { ok: true as const, json: () => bodyPromise };

  return {
    promise,
    bodyPromise,
    resolveResponse: () => resolveResponsePromise(response),
    resolveBody: resolveBodyPromise,
  };
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

  it("announces primary dashboard empty states only after asynchronous bodies leave loading", async () => {
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
      emailsResponse.resolveResponse();
      pendingRepliesResponse.resolveResponse();
      tasksResponse.resolveResponse();
      await Promise.all([
        emailsResponse.promise,
        pendingRepliesResponse.promise,
        tasksResponse.promise,
      ]);
    });

    expect(container.textContent).toContain("답변 대기 메일을 불러오는 중...");
    expect(container.textContent).toContain("작업을 불러오는 중...");
    expect(container.textContent).toContain("메일을 불러오는 중...");
    for (const copy of [
      "답변 대기 중인 보낸 메일이 없습니다.",
      "대기 작업이 없습니다.",
      "수신된 메일이 없습니다.",
    ]) {
      expect(statusWithText(container, copy), copy).toBeNull();
    }

    await act(async () => {
      emailsResponse.resolveBody({ emails: [] });
      pendingRepliesResponse.resolveBody({ emails: [] });
      tasksResponse.resolveBody([]);
      await Promise.all([
        emailsResponse.bodyPromise,
        pendingRepliesResponse.bodyPromise,
        tasksResponse.bodyPromise,
      ]);
    });

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
