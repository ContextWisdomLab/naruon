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
  for (let index = 0; index < 20; index += 1) {
    if (condition()) return;
    await flushAsyncWork();
  }
  throw new Error("waitForCondition timed out after 20 attempts");
}

function emptySourceEvidenceResponse(url: string) {
  if (
    url.endsWith("/api/calendar/writeback-sources") ||
    url.endsWith("/api/webdav/folders")
  ) {
    return Promise.resolve({
      ok: true,
      json: async () => ([]),
    });
  }
  return null;
}

function emptyCalendarCandidateSearchResponse(url: string) {
  if (url.endsWith("/api/search")) {
    return Promise.resolve({
      ok: true,
      json: async () => ({ results: [] }),
    });
  }
  return null;
}

describe("WorkspaceHome Today dashboard", () => {
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

  it("loads pending sent-mail replies through signed session headers", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    const fetchCalls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      fetchCalls.push({ url, init });
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [
              {
                id: 301,
                subject: "벤더 계약 답변 요청",
                sender: "Seongho <user@naruon.ai>",
                date: "2026-05-17T09:00:00Z",
                snippet: "계약 검토 회신 기한이 지나 작업 보드와 연결해야 합니다.",
                requires_reply: true,
              },
            ],
          }),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [
              {
                id: 101,
                subject: "고객 계약 승인 대기",
                sender: "legal@example.com",
                date: "2026-05-17T09:00:00Z",
                snippet: "오늘 승인해야 하는 계약 검토 요청",
                unread: true,
              },
            ],
          }),
        });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([]),
        });
      }
      const sourceEvidenceResponse = emptySourceEvidenceResponse(url);
      if (sourceEvidenceResponse) return sourceEvidenceResponse;
      const calendarCandidateResponse = emptyCalendarCandidateSearchResponse(url);
      if (calendarCandidateResponse) return calendarCandidateResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("벤더 계약 답변 요청") ?? false);

    expect(container.textContent).toContain("답변 대기 메일");
    expect(container.textContent).toContain("계약 검토 회신 기한");
    const pendingCall = fetchCalls.find((call) => call.url.endsWith("/api/emails/pending-replies?limit=3"));
    expect(pendingCall).toBeDefined();
    expect(pendingCall?.init?.credentials).toBe("same-origin");
    const headers = pendingCall?.init?.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    expect(headers["X-User-Id"]).toBeUndefined();
    expect(headers["X-Organization-Id"]).toBeUndefined();
    expect(headers["X-Dev-Auth-Token"]).toBeUndefined();
  });

  it("shows a retryable unavailable state without presenting failed data as empty", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    let primaryDataAvailable = false;
    const primaryCalls: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (
        url.endsWith("/api/emails")
        || url.endsWith("/api/emails/pending-replies?limit=3")
        || url.endsWith("/api/tasks")
      ) {
        primaryCalls.push(url);
        if (!primaryDataAvailable) return Promise.reject(new Error("backend unavailable"));
        if (url.endsWith("/api/emails")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ emails: [{ id: 101, subject: "복구된 고객 메일", sender: "customer@example.com", date: "2026-05-17T09:00:00Z", snippet: "계약 확인" }] }),
          });
        }
        return Promise.resolve({ ok: true, json: async () => url.endsWith("/api/tasks") ? [] : ({ emails: [] }) });
      }
      const sourceEvidenceResponse = emptySourceEvidenceResponse(url);
      if (sourceEvidenceResponse) return sourceEvidenceResponse;
      const calendarCandidateResponse = emptyCalendarCandidateSearchResponse(url);
      if (calendarCandidateResponse) return calendarCandidateResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("업무 현황을 모두 불러오지 못했습니다.") ?? false);

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("다시 시도");
    expect(container.textContent).toContain("최근 메일을 확인하지 못했습니다.");
    expect(container.textContent).not.toContain("수신된 메일이 없습니다.");

    const callsBeforeRetry = primaryCalls.length;
    primaryDataAvailable = true;
    await act(async () => {
      container?.querySelector<HTMLButtonElement>('[role="alert"] button')?.click();
    });
    await waitForCondition(() => primaryCalls.length === callsBeforeRetry + 3);
    await waitForCondition(() => container?.querySelector('[role="alert"]') === null);

    expect(container.textContent).toContain("복구된 고객 메일");
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it("preserves project evidence when only calendar sources fail", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/calendar/writeback-sources")) {
        return Promise.reject(new Error("calendar unavailable"));
      }
      if (url.endsWith("/api/webdav/folders")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([{
            folder_uid: "project-folder-1",
            project_name: "계약 검토",
            webdav_path: "/contracts",
          }]),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({ ok: true, json: async () => ({ emails: [] }) });
      }
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({ ok: true, json: async () => ({ emails: [] }) });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({ ok: true, json: async () => ([]) });
      }
      const calendarCandidateResponse = emptyCalendarCandidateSearchResponse(url);
      if (calendarCandidateResponse) return calendarCandidateResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("일정 원본 목록 응답을 확인할 수 없습니다.") ?? false);

    const metrics = container.querySelector<HTMLElement>('[aria-label="홈 지표"]');
    expect(metrics?.textContent).toContain("일정 원본오류");
    expect(metrics?.textContent).toContain("프로젝트 원본1");
    expect(metrics?.textContent).not.toContain("프로젝트 원본오류");
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("다시 시도");
  });

  it("creates overdue reply follow-up tasks from the Today dashboard with signed headers", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    const publicIdentityHeaders = [
      "x-user-id",
      "x-organization-id",
      "x-group-id",
      "x-group-ids",
      "x-user-role",
      "x-dev-auth-token",
    ];
    const fetchCalls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      fetchCalls.push({ url, init });
      if (url.endsWith("/api/tasks/reply-sla-escalations")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            evaluated: 2,
            created: 1,
            policy: { overdue_hours: 48 },
            tasks: [],
          }),
        });
      }
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [
              {
                id: 301,
                subject: "벤더 계약 답변 요청",
                sender: "Seongho <user@naruon.ai>",
                date: "2026-05-17T09:00:00Z",
                snippet: "계약 검토 회신 기한이 지나 작업 보드와 연결해야 합니다.",
                requires_reply: true,
              },
            ],
          }),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ emails: [] }),
        });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([]),
        });
      }
      const sourceEvidenceResponse = emptySourceEvidenceResponse(url);
      if (sourceEvidenceResponse) return sourceEvidenceResponse;
      const calendarCandidateResponse = emptyCalendarCandidateSearchResponse(url);
      if (calendarCandidateResponse) return calendarCandidateResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("벤더 계약 답변 요청") ?? false);

    const escalationButton = container.querySelector<HTMLButtonElement>(
      'button[aria-label="홈에서 보낸 메일 미답변 팔로업 작업 생성"]',
    );
    expect(escalationButton).not.toBeNull();
    await act(async () => {
      escalationButton?.click();
    });
    await waitForCondition(() => container?.textContent?.includes("1개 팔로업 작업 생성") ?? false);

    const escalationCall = fetchCalls.find((call) => call.url.endsWith("/api/tasks/reply-sla-escalations"));
    expect(escalationCall).toBeDefined();
    expect(escalationCall?.init?.method).toBe("POST");
    expect(escalationCall?.init?.credentials).toBe("same-origin");
    expect(JSON.parse(String(escalationCall?.init?.body))).toEqual({ overdue_hours: 48 });
    const headers = escalationCall?.init?.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    for (const headerName of publicIdentityHeaders) {
      expect(Object.keys(headers).some((key) => key.toLowerCase() === headerName)).toBe(false);
    }
    expect(container.textContent).toContain("1개 팔로업 작업 생성, 2개 답변 대기 확인");
  });

  it("routes Today dashboard task calendar and quick actions to implemented workspaces", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ emails: [] }),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [
              {
                id: 101,
                subject: "고객 계약 승인 대기",
                sender: "legal@example.com",
                date: "2026-05-17T09:00:00Z",
                snippet: "오늘 승인해야 하는 계약 검토 요청",
                unread: true,
              },
            ],
          }),
        });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([
            {
              id: "task-home-route",
              title: "계약 승인 확인",
              status: "open",
              priority: "high",
              created_at: "2026-05-17T09:00:00Z",
              updated_at: "2026-05-17T09:00:00Z",
            },
          ]),
        });
      }
      const sourceEvidenceResponse = emptySourceEvidenceResponse(url);
      if (sourceEvidenceResponse) return sourceEvidenceResponse;
      const calendarCandidateResponse = emptyCalendarCandidateSearchResponse(url);
      if (calendarCandidateResponse) return calendarCandidateResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("계약 승인 확인") ?? false);

    const linkHrefByText = (label: string) =>
      Array.from(container?.querySelectorAll<HTMLAnchorElement>("a") ?? [])
        .find((link) => link.textContent?.includes(label))
        ?.getAttribute("href");

    expect(linkHrefByText("작업 바로가기")).toBe("/tasks");
    expect(linkHrefByText("전체 작업 보기")).toBe("/tasks");
    expect(linkHrefByText("일정 조율하기")).toBe("/calendar");
    expect(linkHrefByText("열기")).toBe("/mail?id=101");
    expect(
      Array.from(container?.querySelectorAll("button") ?? [])
        .some((button) => button.textContent?.includes("보류")),
    ).toBe(false);

    const quickActions = container.querySelector<HTMLElement>('[aria-label="홈 빠른 실행"]');
    expect(quickActions).not.toBeNull();
    expect(Array.from(quickActions?.querySelectorAll("button") ?? [])).toHaveLength(0);
    expect(linkHrefByText("메일함 열기")).toBe("/mail");
    expect(linkHrefByText("보낸 메일 답변 추적")).toBe("/mail?folder=sent");
    expect(linkHrefByText("일정 후보 검토")).toBe("/calendar");
    expect(linkHrefByText("실행 항목 보드")).toBe("/tasks");
    expect(linkHrefByText("프로젝트 의사결정")).toBe("/projects");
    expect(linkHrefByText("AI 허브")).toBe("/ai-hub");
    expect(linkHrefByText("데이터 품질 점검")).toBe("/data");
    expect(linkHrefByText("보안 감사 로그")).toBe("/security");
  });

  it("marks a Today dashboard task done through the signed task API", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    const fetchCalls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      fetchCalls.push({ url, init });
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ emails: [] }),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ emails: [] }),
        });
      }
      if (url.endsWith("/api/tasks/task-home-toggle")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: "task-home-toggle",
            title: "계약 승인 확인",
            status: "done",
            priority: "high",
            created_at: "2026-05-17T09:00:00Z",
            updated_at: "2026-05-17T10:00:00Z",
          }),
        });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([
            {
              id: "task-home-toggle",
              title: "계약 승인 확인",
              status: "open",
              priority: "high",
              created_at: "2026-05-17T09:00:00Z",
              updated_at: "2026-05-17T09:00:00Z",
            },
          ]),
        });
      }
      const sourceEvidenceResponse = emptySourceEvidenceResponse(url);
      if (sourceEvidenceResponse) return sourceEvidenceResponse;
      const calendarCandidateResponse = emptyCalendarCandidateSearchResponse(url);
      if (calendarCandidateResponse) return calendarCandidateResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("계약 승인 확인") ?? false);

    const taskCheckbox = container.querySelector<HTMLInputElement>(
      'input[aria-label="계약 승인 확인 작업 선택"]',
    );
    expect(taskCheckbox).not.toBeNull();
    expect(taskCheckbox?.checked).toBe(false);

    await act(async () => {
      taskCheckbox?.click();
    });
    await waitForCondition(() => container?.textContent?.includes("계약 승인 확인 작업을 완료 처리했습니다.") ?? false);

    const patchCall = fetchCalls.find((call) => call.url.endsWith("/api/tasks/task-home-toggle"));
    expect(patchCall?.init?.method).toBe("PATCH");
    expect(patchCall?.init?.credentials).toBe("same-origin");
    expect(JSON.parse(String(patchCall?.init?.body))).toEqual({ status: "done" });
    const headers = patchCall?.init?.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    for (const headerName of [
      "x-user-id",
      "x-organization-id",
      "x-group-id",
      "x-group-ids",
      "x-user-role",
      "x-dev-auth-token",
    ]) {
      expect(Object.keys(headers).some((key) => key.toLowerCase() === headerName)).toBe(false);
    }
  });

  it("keeps Today dashboard task update feedback keyed per task", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ emails: [] }),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ emails: [] }),
        });
      }
      if (url.endsWith("/api/tasks/task-alpha")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: "task-alpha",
            title: "계약 승인 확인",
            status: "done",
            priority: "high",
            created_at: "2026-05-17T09:00:00Z",
            updated_at: "2026-05-17T10:00:00Z",
          }),
        });
      }
      if (url.endsWith("/api/tasks/task-beta")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: "task-beta",
            title: "회의록 공유",
            status: "done",
            priority: "normal",
            created_at: "2026-05-17T09:00:00Z",
            updated_at: "2026-05-17T10:00:00Z",
          }),
        });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([
            {
              id: "task-alpha",
              title: "계약 승인 확인",
              status: "open",
              priority: "high",
              created_at: "2026-05-17T09:00:00Z",
              updated_at: "2026-05-17T09:00:00Z",
            },
            {
              id: "task-beta",
              title: "회의록 공유",
              status: "open",
              priority: "normal",
              created_at: "2026-05-17T09:00:00Z",
              updated_at: "2026-05-17T09:00:00Z",
            },
          ]),
        });
      }
      const sourceEvidenceResponse = emptySourceEvidenceResponse(url);
      if (sourceEvidenceResponse) return sourceEvidenceResponse;
      const calendarCandidateResponse = emptyCalendarCandidateSearchResponse(url);
      if (calendarCandidateResponse) return calendarCandidateResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("회의록 공유") ?? false);

    const contractCheckbox = container.querySelector<HTMLInputElement>(
      'input[aria-label="계약 승인 확인 작업 선택"]',
    );
    const notesCheckbox = container.querySelector<HTMLInputElement>(
      'input[aria-label="회의록 공유 작업 선택"]',
    );
    expect(contractCheckbox).not.toBeNull();
    expect(notesCheckbox).not.toBeNull();

    await act(async () => {
      contractCheckbox?.click();
      notesCheckbox?.click();
    });
    await waitForCondition(() => (
      (container?.textContent?.includes("계약 승인 확인 작업을 완료 처리했습니다.") ?? false)
      && (container?.textContent?.includes("회의록 공유 작업을 완료 처리했습니다.") ?? false)
    ));
  });

  it.each([
    ["etag-home-1", "원본 변경 비교 가능"],
    [null, "변경 전 원본 확인 필요"],
  ])("backs Today dashboard metrics with source evidence (comparison: %s)", async (sourceEtag, comparisonLabel) => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    const publicIdentityHeaders = [
      "x-user-id",
      "x-organization-id",
      "x-group-id",
      "x-group-ids",
      "x-user-role",
      "x-dev-auth-token",
    ];
    const fetchCalls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      fetchCalls.push({ url, init });
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ emails: [] }),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [
              {
                id: 101,
                subject: "고객 계약 승인 대기",
                sender: "legal@example.com",
                date: "2026-05-17T09:00:00Z",
                snippet: "오늘 승인해야 하는 계약 검토 요청",
                unread: true,
              },
            ],
          }),
        });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([
            {
              id: "task-source-open",
              title: "<script>계약 승인 확인</script>",
              status: "open",
              priority: "high",
              created_at: "2026-05-17T09:00:00Z",
              updated_at: "2026-05-17T09:00:00Z",
            },
            {
              id: "task-source-done",
              title: "첨부 근거 정리",
              status: "done",
              priority: "low",
              created_at: "2026-05-17T09:00:00Z",
              updated_at: "2026-05-17T09:00:00Z",
            },
          ]),
        });
      }
      if (url.endsWith("/api/calendar/writeback-sources")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([
            {
              source_id: "caldav-primary",
              provider: "Primary CalDAV",
              protocol: "caldav",
              capabilities: ["read", "write"],
              writeback_enabled: true,
              etag: sourceEtag,
            },
            {
              source_id: "calendar-readonly",
              provider: "Read-only Calendar",
              protocol: "local",
              capabilities: ["read"],
              writeback_enabled: false,
            },
          ]),
        });
      }
      if (url.endsWith("/api/webdav/folders")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([
            {
              folder_uid: "folder-roadmap",
              project_name: "Naruon Roadmap",
              webdav_path: "/Projects/Naruon_Roadmap",
            },
          ]),
        });
      }
      if (url.endsWith("/api/search")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            results: [
              {
                id: 601,
                subject: "엔터프라이즈 데모 일정 조율",
                sender: "sales@example.com",
                date: "2026-05-18T11:00:00Z",
                snippet: "고객 데모 후보 시간을 확정해야 합니다.",
              },
            ],
          }),
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("고객 계약 승인 대기") ?? false);

    expect(container.textContent).toContain("일정 원본");
    expect(container.textContent).toContain("2");
    expect(container.textContent).toContain("1개 일정 반영 가능");
    expect(container.textContent).toContain("일정 원본 1");
    expect(container.textContent).toContain(comparisonLabel);
    expect(container.textContent).not.toContain("충돌 토큰");
    expect(container.textContent).not.toContain("source-linked");
    expect(container.querySelector('article[aria-label="대기 작업"]')?.textContent).toContain("미완료");
    expect(container.textContent).toContain("프로젝트 원본");
    expect(container.textContent).toContain("1개 WebDAV 폴더");
    expect(container.textContent).toContain("작업 완료율");
    expect(container.textContent).toContain("50%");
    expect(container.textContent).toContain("1/2 완료");
    expect(container.textContent).toContain("계약 승인 확인");
    expect(container.textContent).toContain("일정 조율 후보 1건");
    expect(container.textContent).toContain("엔터프라이즈 데모 일정 조율");
    expect(container.textContent).toContain("고객 데모 후보 시간을 확정해야 합니다.");
    expect(container.textContent).not.toContain("오늘 일정");
    expect(container.textContent).not.toContain("진행 중 프로젝트");
    expect(container.textContent).not.toContain("이번 주 목표 진행률");
    expect(container.textContent).not.toContain("회의 2건 예정");
    expect(container.textContent).not.toContain("일정 충돌 알림");
    expect(container.textContent).not.toContain("68%");
    expect(container.textContent).not.toContain("어제 대비");
    expect(container.textContent).not.toContain("<script>");
    expect(container.textContent).not.toContain("caldav-primary");
    expect(container.textContent).not.toContain("calendar-readonly");
    expect(container.textContent).not.toContain("Primary CalDAV");
    expect(container.textContent).not.toContain("Read-only Calendar");

    const calendarSourceCall = fetchCalls.find((call) => call.url.endsWith("/api/calendar/writeback-sources"));
    const projectFolderCall = fetchCalls.find((call) => call.url.endsWith("/api/webdav/folders"));
    const calendarCandidateCall = fetchCalls.find((call) => call.url.endsWith("/api/search"));
    expect(calendarCandidateCall?.init?.method).toBe("POST");
    expect(JSON.parse(String(calendarCandidateCall?.init?.body))).toEqual({
      query: "일정 충돌 일정 조율 회의 후보",
      limit: 3,
    });
    for (const sourceCall of [calendarSourceCall, projectFolderCall, calendarCandidateCall]) {
      expect(sourceCall).toBeDefined();
      expect(sourceCall?.init?.credentials).toBe("same-origin");
      const headers = sourceCall?.init?.headers as Record<string, string>;
      expect(headers.Authorization).toBeUndefined();
      for (const headerName of publicIdentityHeaders) {
        expect(Object.keys(headers).some((key) => key.toLowerCase() === headerName)).toBe(false);
      }
    }
  });

  it("shows an explicit source evidence error instead of a false empty calendar state", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ emails: [] }),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [
              {
                id: 101,
                subject: "고객 계약 승인 대기",
                sender: "legal@example.com",
                date: "2026-05-17T09:00:00Z",
                snippet: "오늘 승인해야 하는 계약 검토 요청",
                unread: true,
              },
            ],
          }),
        });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([]),
        });
      }
      if (url.endsWith("/api/calendar/writeback-sources") || url.endsWith("/api/webdav/folders")) {
        return Promise.reject(new Error("source registry unavailable"));
      }
      const calendarCandidateResponse = emptyCalendarCandidateSearchResponse(url);
      if (calendarCandidateResponse) return calendarCandidateResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<WorkspaceHome forcedStartupView="dashboard" />);
    });
    await waitForCondition(() => container?.textContent?.includes("일정 원본 목록 확인에 실패했습니다.") ?? false);

    expect(container.textContent).toContain("일정 원본 확인 필요");
    expect(container.textContent).toContain("오류");
    expect(container.textContent).toContain("일정 원본 목록 응답을 확인할 수 없습니다.");
    expect(container.textContent).not.toContain("연결된 일정 원본이 없습니다.");
  });
});
