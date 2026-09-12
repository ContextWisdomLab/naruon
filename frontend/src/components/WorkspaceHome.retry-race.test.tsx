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

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function waitForCondition(condition: () => boolean) {
  for (let index = 0; index < 30; index += 1) {
    if (condition()) return;
    await flushAsyncWork();
  }
  throw new Error("waitForCondition timed out after 30 attempts");
}

describe("WorkspaceHome dashboard retry ordering", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    const mountedRoot = root;
    if (mountedRoot) {
      act(() => mountedRoot.unmount());
    }
    root = null;
    container?.remove();
    container = null;
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("cancels the discarded StrictMode mount without cancelling the active mount", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    const dashboardSignals: AbortSignal[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/api/search")) {
        return Promise.resolve({ ok: true, json: async () => ({ results: [] }) });
      }
      expect(init?.signal).toBeDefined();
      dashboardSignals.push(init!.signal!);
      return new Promise((_resolve, reject) => {
        init!.signal!.addEventListener("abort", () => reject(init!.signal!.reason), { once: true });
      });
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<React.StrictMode><WorkspaceHome forcedStartupView="dashboard" /></React.StrictMode>);
    });
    expect(dashboardSignals).toHaveLength(10);
    expect(dashboardSignals.slice(0, 5).every((signal) => signal.aborted)).toBe(true);
    expect(dashboardSignals.slice(5).every((signal) => !signal.aborted)).toBe(true);
    expect(container.querySelector('[role="alert"]')).toBeNull();
    await act(async () => root?.unmount());
    root = null;
    expect(dashboardSignals.every((signal) => signal.aborted)).toBe(true);
  });

  it("keeps a recovered retry result when an older request resolves later", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));

    const firstEmails = deferred<{ ok: boolean; json: () => Promise<unknown> }>();
    let emailCallCount = 0;
    let calendarCallCount = 0;
    const dashboardSignals: AbortSignal[] = [];

    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (!url.endsWith("/api/search")) {
        expect(init?.signal).toBeDefined();
        dashboardSignals.push(init!.signal!);
      }
      if (url.endsWith("/api/emails")) {
        emailCallCount += 1;
        if (emailCallCount === 1) return firstEmails.promise;
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [{
              id: 202,
              subject: "재시도 후 최신 메일",
              sender: "customer@example.com",
              date: "2026-09-05T08:00:00Z",
              snippet: "최신 결과",
            }],
          }),
        });
      }
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({ ok: true, json: async () => ({ emails: [] }) });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.endsWith("/api/calendar/writeback-sources")) {
        calendarCallCount += 1;
        if (calendarCallCount === 1) return Promise.reject(new Error("calendar unavailable"));
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.endsWith("/api/webdav/folders")) {
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
    await waitForCondition(() => container?.querySelector('[role="alert"]') !== null);

    await act(async () => {
      container?.querySelector<HTMLButtonElement>('[role="alert"] button')?.click();
    });
    await waitForCondition(() => container?.textContent?.includes("재시도 후 최신 메일") ?? false);
    expect(dashboardSignals).toHaveLength(10);
    expect(dashboardSignals.slice(0, 5).every((signal) => signal.aborted)).toBe(true);
    expect(dashboardSignals.slice(5).every((signal) => !signal.aborted)).toBe(true);

    firstEmails.resolve({
      ok: true,
      json: async () => ({
        emails: [{
          id: 101,
          subject: "늦게 도착한 이전 메일",
          sender: "stale@example.com",
          date: "2026-09-05T07:00:00Z",
          snippet: "이전 결과",
        }],
      }),
    });
    await flushAsyncWork();
    await flushAsyncWork();

    expect(container.textContent).toContain("재시도 후 최신 메일");
    expect(container.textContent).not.toContain("늦게 도착한 이전 메일");
    expect(emailCallCount).toBe(2);
    expect(calendarCallCount).toBe(2);
    await act(async () => root?.unmount());
    root = null;
    expect(dashboardSignals.every((signal) => signal.aborted)).toBe(true);
  });
});
