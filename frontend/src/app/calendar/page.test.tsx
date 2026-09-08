/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a>,
}));

vi.mock("lucide-react", () => ({
  CalendarDays: () => <svg aria-hidden="true" />,
  CheckCircle2: () => <svg aria-hidden="true" />,
  Clock: () => <svg aria-hidden="true" />,
  Loader2: () => <svg aria-hidden="true" />,
  Users: () => <svg aria-hidden="true" />,
  Video: () => <svg aria-hidden="true" />,
  Plus: () => <svg aria-hidden="true" />,
  ChevronLeft: () => <svg aria-hidden="true" />,
  ChevronRight: () => <svg aria-hidden="true" />,
  Settings: () => <svg aria-hidden="true" />,
  X: () => <svg aria-hidden="true" />,
  Paperclip: () => <svg aria-hidden="true" />,
}));

import CalendarPage from "./page";

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: async () => body,
  } as Response;
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

const calendarSourceList = [
  {
    source_id: "caldav-primary",
    provider: "Customer CalDAV",
    protocol: "caldav",
    owner_id: "user-1",
    organization_id: "org-acme",
    capabilities: ["read", "write", "etag"],
    writeback_enabled: true,
    etag: "etag-caldav-1",
  },
  {
    source_id: "caldav-team",
    provider: "Team CalDAV",
    protocol: "caldav",
    owner_id: "user-1",
    organization_id: "org-acme",
    capabilities: ["read", "write", "etag"],
    writeback_enabled: true,
    etag: "etag-team-2",
  },
];

describe("CalendarPage", () => {
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

  it("renders monthly weekly detail coordination candidate and CalDAV writeback workspaces", () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(calendarSourceList)));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });

    expect(container.textContent).toContain("새 일정");
    expect(container.textContent).toContain("고객 원본 일정 반영 의도");
    expect(container.textContent).not.toContain("뷰는 아직 구현 중입니다");
    expect(container.querySelector('button[aria-label="이전 달"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="다음 달"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="설정"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="닫기"]')).not.toBeNull();
  });

  it("exposes the calendar view switcher as a keyboard-navigable tablist", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(calendarSourceList)));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });
    await flushAsyncWork();

    const tablist = container.querySelector<HTMLElement>('[role="tablist"][aria-label="일정 보기 방식"]');
    expect(tablist).not.toBeNull();
    const tabs = Array.from(tablist?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? []);
    expect(tabs.map((tab) => tab.textContent)).toEqual(["월간 캘린더", "주간 캘린더", "일정 상세", "회의 조율", "일정 후보"]);

    const monthlyTab = tabs[0];
    expect(monthlyTab?.getAttribute("aria-selected")).toBe("true");
    expect(monthlyTab?.tabIndex).toBe(0);
    expect(monthlyTab?.getAttribute("aria-controls")).toBe("calendar-view-panel");
    const panel = container.querySelector<HTMLElement>('#calendar-view-panel[role="tabpanel"]');
    expect(panel?.getAttribute("aria-labelledby")).toBe(monthlyTab?.id);
    for (const tab of tabs.slice(1)) {
      expect(tab.getAttribute("aria-selected")).toBe("false");
      expect(tab.tabIndex).toBe(-1);
    }

    act(() => {
      monthlyTab?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    });
    await flushAsyncWork();

    const weeklyTab = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
      .find((tab) => tab.textContent === "주간 캘린더");
    expect(weeklyTab?.getAttribute("aria-selected")).toBe("true");
    expect(weeklyTab?.tabIndex).toBe(0);
    expect(container.querySelector<HTMLElement>('#calendar-view-panel[role="tabpanel"]')?.getAttribute("aria-labelledby")).toBe(weeklyTab?.id);
  });

  it("filters rendered calendar events when a calendar visibility checkbox changes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(calendarSourceList)));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("제품 리뷰");
    const productCalendarToggle = container.querySelector<HTMLInputElement>(
      'input[aria-label="제품 개발팀 캘린더 표시 토글"]',
    );
    expect(productCalendarToggle).not.toBeNull();
    expect(productCalendarToggle?.checked).toBe(true);

    await act(async () => {
      productCalendarToggle?.click();
    });
    await flushAsyncWork();

    expect(productCalendarToggle?.checked).toBe(false);
    expect(container.textContent).not.toContain("제품 리뷰");
    expect(container.textContent).toContain("출시 회의");
  });

  it("creates a signed customer-owned calendar writeback intent", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/calendar/writeback-sources") {
        expect(init?.method).toBeUndefined();
        expect(init?.credentials).toBe("same-origin");
        expect(init?.headers).toEqual(expect.objectContaining({
          "Content-Type": "application/json",
        }));
        expect(init?.headers).not.toHaveProperty("Authorization");
        return jsonResponse(calendarSourceList);
      }
      expect(String(input)).toBe("/api/calendar/writeback-intent");
      expect(init?.method).toBe("POST");
      expect(init?.credentials).toBe("same-origin");
      expect(init?.headers).toEqual(expect.objectContaining({
        "Content-Type": "application/json",
      }));
      expect(init?.headers).not.toHaveProperty("Authorization");
      const requestHeaders = init?.headers as Record<string, string>;
      const normalizedHeaderNames = new Set(Object.keys(requestHeaders).map((headerName) => headerName.toLowerCase()));
      for (const publicHeader of [
        "x-user-id",
        "x-organization-id",
        "x-group-id",
        "x-group-ids",
        "x-user-role",
        "x-dev-auth-token",
      ]) {
        expect(normalizedHeaderNames.has(publicHeader)).toBe(false);
      }
      expect(JSON.parse(String(init?.body))).toEqual({
        action: "create",
        summary: "Naruon 일정 후보 writeback intent 점검",
        target_source_id: "caldav-primary",
      });
      return jsonResponse({
        workspace_id: "workspace-org-acme",
        target_source_id: "caldav-primary",
        protocol: "caldav",
        writeback_mode: "customer_owned",
        requires_if_match: false,
        if_match: null,
        provenance: {
          created_by: "user-1",
          source_provider: "Customer CalDAV",
          source_protocol: "caldav",
        },
        audit_event: "calendar.writeback_intent.created",
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });
    await flushAsyncWork();
    expect(container.textContent).toContain("일정 원본 1");
    expect(container.textContent).toContain("충돌 토큰 있음");
    expect(container.textContent).not.toContain("Customer CalDAV");
    expect(container.textContent).not.toContain("etag=etag-caldav-1");
    expect(container.textContent).not.toContain("caldav-primary");

    const button = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes("새 일정 intent 점검"));
    expect(button).toBeTruthy();
    await act(async () => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("고객 원본 계정 반영");
    expect(container.textContent).toContain("CalDAV 원본 선택됨");
    expect(container.textContent).toContain("선택한 일정 원본");
    expect(container.textContent).toContain("감사 근거");
    expect(container.textContent).toContain("기록됨");
    expect(container.textContent).not.toContain("customer_owned");
    expect(container.textContent).not.toContain("caldav-primary");
    expect(container.textContent).not.toContain("calendar.writeback_intent.created");
  });

  it("lets the user choose a specific customer-owned calendar source before intent creation", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/calendar/writeback-sources") {
        expect(init?.credentials).toBe("same-origin");
        expect(init?.headers).toEqual(expect.objectContaining({
          "Content-Type": "application/json",
        }));
        expect(init?.headers).not.toHaveProperty("Authorization");
        return jsonResponse(calendarSourceList);
      }
      expect(String(input)).toBe("/api/calendar/writeback-intent");
      expect(init?.credentials).toBe("same-origin");
      expect(init?.headers).toEqual(expect.objectContaining({
        "Content-Type": "application/json",
      }));
      expect(init?.headers).not.toHaveProperty("Authorization");
      expect(JSON.parse(String(init?.body))).toEqual({
        action: "create",
        summary: "Naruon 일정 후보 writeback intent 점검",
        target_source_id: "caldav-team",
      });
      return jsonResponse({
        workspace_id: "workspace-org-acme",
        target_source_id: "caldav-team",
        protocol: "caldav",
        writeback_mode: "customer_owned",
        requires_if_match: false,
        if_match: null,
        provenance: {
          created_by: "user-1",
          source_provider: "Team CalDAV",
          source_protocol: "caldav",
        },
        audit_event: "calendar.writeback_intent.created",
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });
    await flushAsyncWork();

    const teamSourceButton = container.querySelector<HTMLButtonElement>(
      'button[aria-label="일정 원본 2 일정 반영 가능 선택"]',
    );
    expect(teamSourceButton).toBeTruthy();
    await act(async () => {
      teamSourceButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    const createButton = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes("새 일정 intent 점검"));
    await act(async () => {
      createButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("일정 원본 2");
    expect(container.textContent).toContain("선택한 일정 원본");
    expect(container.textContent).not.toContain("caldav-team");
    expect(container.textContent).not.toContain("Team CalDAV");
  });

  it("lets the user explicitly request provider execution for an ETag-guarded calendar update", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/calendar/writeback-sources") {
        expect(init?.credentials).toBe("same-origin");
        expect(init?.headers).toEqual(expect.objectContaining({
          "Content-Type": "application/json",
        }));
        expect(init?.headers).not.toHaveProperty("Authorization");
        return jsonResponse(calendarSourceList);
      }
      expect(String(input)).toBe("/api/calendar/writeback-intent");
      expect(init?.method).toBe("POST");
      expect(init?.credentials).toBe("same-origin");
      const requestHeaders = init?.headers as Record<string, string>;
      const normalizedHeaderNames = new Set(Object.keys(requestHeaders).map((headerName) => headerName.toLowerCase()));
      for (const publicHeader of [
        "x-user-id",
        "x-organization-id",
        "x-group-id",
        "x-group-ids",
        "x-user-role",
        "x-dev-auth-token",
      ]) {
        expect(normalizedHeaderNames.has(publicHeader)).toBe(false);
      }
      expect(JSON.parse(String(init?.body))).toEqual({
        action: "update",
        summary: "Naruon 기존 일정 ETag/If-Match 충돌 점검",
        target_source_id: "caldav-primary",
        execute_provider: true,
      });
      return jsonResponse({
        workspace_id: "workspace-org-acme",
        target_source_id: "caldav-primary",
        protocol: "caldav",
        writeback_mode: "customer_owned",
        requires_if_match: true,
        if_match: "etag-caldav-1",
        provenance: {
          created_by: "user-1",
          source_provider: "Customer CalDAV",
          source_protocol: "caldav",
        },
        audit_event: "calendar.writeback.dispatch_failed",
        provider_write_executed: false,
        status: "queued",
        runner_request_id: "runner-request-1",
        provider_status: null,
        retry_item_uid: "retry-item-1",
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });
    await flushAsyncWork();

    const executeButton = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes("ETag 실행 요청"));
    expect(executeButton).toBeTruthy();
    await act(async () => {
      executeButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("커넥터 실행 요청 접수");
    expect(container.textContent).toContain("If-Match 필요");
    expect(container.textContent).toContain("재시도 대기");
    expect(container.textContent).not.toContain("runner-request-1");
    expect(container.textContent).not.toContain("retry-item-1");
    expect(container.textContent).not.toContain("calendar.writeback.dispatch_failed");
  });

  it("does not post writeback intent before source registry readiness", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      expect(String(input)).toBe("/api/calendar/writeback-sources");
      return new Promise<Response>(() => undefined);
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });

    const button = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes("새 일정 intent 점검"));
    await act(async () => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/calendar/writeback-sources");
    expect(container.textContent).toContain("일정 원본 목록을 확인하는 중입니다.");
  });

  it("shows a loading state while writeback intent is pending", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input) === "/api/calendar/writeback-sources") {
        return Promise.resolve(jsonResponse(calendarSourceList));
      }
      return new Promise(() => undefined);
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });
    await flushAsyncWork();

    const button = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes("새 일정 intent 점검"));
    await act(async () => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("/api/calendar/writeback-intent");
    expect(button?.getAttribute("aria-busy")).toBe("true");
    expect(button?.textContent).toContain("처리 중");
    const updateButton = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes("ETag 업데이트 점검"));
    expect(updateButton?.getAttribute("aria-busy")).toBe("false");
    expect(container.textContent).toContain("ETag 실행 요청");
    expect(container.textContent).toContain("일정 반영 의도 요청 중입니다.");
  });

  it("distinguishes no-source and ETag conflict writeback errors", async () => {
    const responses = [
      jsonResponse(calendarSourceList),
      jsonResponse({ detail: "No customer-owned writeback source is available" }, false, 422),
      jsonResponse({ detail: "ETag is required for writeback updates" }, false, 409),
    ];
    vi.stubGlobal("fetch", vi.fn(async () => responses.shift() ?? jsonResponse({}, false, 500)));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });
    await flushAsyncWork();

    const createButton = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes("새 일정 intent 점검"));
    await act(async () => {
      createButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();
    expect(container.textContent).toContain("원본 CalDAV/CardDAV/WebDAV 계정이 없어");

    const updateButton = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes("ETag 업데이트 점검"));
    await act(async () => {
      updateButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();
    expect(container.textContent).toContain("ETag/If-Match 충돌");
  });

  it("surfaces selectable signed calendar sources on the coordination view", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe("/api/calendar/writeback-sources");
      expect(init?.credentials).toBe("same-origin");
      expect(init?.headers).not.toHaveProperty("Authorization");
      const requestHeaders = (init?.headers ?? {}) as Record<string, string>;
      const normalizedHeaderNames = new Set(Object.keys(requestHeaders).map((headerName) => headerName.toLowerCase()));
      for (const publicHeader of [
        "x-user-id",
        "x-organization-id",
        "x-group-id",
        "x-group-ids",
        "x-user-role",
        "x-dev-auth-token",
      ]) {
        expect(normalizedHeaderNames.has(publicHeader)).toBe(false);
      }
      return jsonResponse(calendarSourceList);
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<CalendarPage />);
    });
    await flushAsyncWork();

    const coordinationTab = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
      .find((tab) => tab.textContent === "회의 조율");
    await act(async () => {
      coordinationTab?.click();
    });
    await flushAsyncWork();
    await flushAsyncWork();

    expect(fetchMock.mock.calls.every(([input]) => String(input) === "/api/calendar/writeback-sources")).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/calendar/conflicts/evaluate")).toBe(false);
    expect(container.textContent).toContain("일정 원본 1");
    expect(container.textContent).toContain("선택한 일정 원본의 서명된 증거만 조율에 사용합니다.");
    expect(container.textContent).not.toContain("확정 제안 vs 취소된 기존 일정");
    expect(container.textContent).not.toContain("이 시간은 비어 있습니다. 일정을 계속 진행하세요.");
    expect(container.textContent).not.toContain("모든 참석자 참석 가능");

    const secondSource = Array.from(container.querySelectorAll<HTMLButtonElement>("button"))
      .find((button) => button.getAttribute("aria-label")?.includes("일정 원본 2"));
    await act(async () => {
      secondSource?.click();
    });
    await flushAsyncWork();

    expect(secondSource?.getAttribute("aria-pressed")).toBe("true");
    expect(container.textContent).toContain("일정 원본 2");
  });
});
