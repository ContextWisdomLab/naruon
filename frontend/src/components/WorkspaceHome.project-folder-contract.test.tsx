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

function stubDesktopViewport() {
  vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
    matches: query.includes("min-width: 1024px") ? false : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })));
}

function successfulDashboardResponse(url: string, projectFolders: unknown[]) {
  if (url.endsWith("/api/webdav/folders")) {
    return Promise.resolve({ ok: true, json: async () => projectFolders });
  }
  if (url.endsWith("/api/calendar/writeback-sources")) {
    return Promise.resolve({ ok: true, json: async () => [] });
  }
  if (url.endsWith("/api/search")) {
    return Promise.resolve({ ok: true, json: async () => ({ results: [] }) });
  }
  if (url.endsWith("/api/emails") || url.endsWith("/api/emails/pending-replies?limit=3")) {
    return Promise.resolve({ ok: true, json: async () => ({ emails: [] }) });
  }
  if (url.endsWith("/api/tasks")) {
    return Promise.resolve({ ok: true, json: async () => [] });
  }
  throw new Error(`Unexpected fetch: ${url}`);
}

describe("WorkspaceHome project-folder response contract", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    const mountedRoot = root;
    if (mountedRoot) act(() => mountedRoot.unmount());
    root = null;
    container?.remove();
    container = null;
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  async function renderDashboard(projectFolders: unknown[]) {
    stubDesktopViewport();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => successfulDashboardResponse(String(input), projectFolders)));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
  }

  it.each([
    null,
    {},
    { folder_uid: 7, project_name: "Project", webdav_path: "/projects/one", owner_user_id: "user-1", organization_id: null },
    { folder_uid: "folder-1", project_name: null, webdav_path: "/projects/one", owner_user_id: "user-1", organization_id: null },
    { folder_uid: "folder-1", project_name: "Project", webdav_path: "/projects/one", organization_id: null },
    { folder_uid: "folder-1", project_name: "Project", webdav_path: "/projects/one", owner_user_id: "user-1", organization_id: 42 },
  ])("fails closed for malformed project-folder member %#", async (member) => {
    await renderDashboard([member]);
    await waitForCondition(() => container?.textContent?.includes("업무 현황을 모두 불러오지 못했습니다.") ?? false);

    const projectFolderCard = container?.querySelector('[aria-label="프로젝트 원본"]');
    expect(projectFolderCard?.textContent).toContain("오류");
    expect(projectFolderCard?.textContent).toContain("확인 필요");
    expect(container?.querySelector('[role="alert"] button')?.textContent).toBe("다시 시도");
  });

  it("keeps a backend-contract project folder available", async () => {
    await renderDashboard([{
      folder_uid: "folder-1",
      project_name: "Project",
      webdav_path: "/projects/one",
      owner_user_id: "user-1",
      organization_id: null,
    }]);
    await waitForCondition(() => container?.querySelector('[aria-label="프로젝트 원본"]')?.textContent?.includes("1") ?? false);

    const projectFolderCard = container?.querySelector('[aria-label="프로젝트 원본"]');
    expect(projectFolderCard?.textContent).not.toContain("오류");
    expect(projectFolderCard?.textContent).toContain("1개");
  });
});
