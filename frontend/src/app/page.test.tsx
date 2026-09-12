/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockEmailSelection = vi.hoisted(() => ({ emailId: 42 }));
const mockDetailCommands = vi.hoisted(() => ({ executions: [] as string[] }));

vi.mock("@/components/EmailList", () => ({
  EmailList: ({ onSelectEmail }: { onSelectEmail: (emailId: number) => void }) => (
    <button type="button" onClick={() => onSelectEmail(mockEmailSelection.emailId)}>메일 선택</button>
  ),
}));

vi.mock("@/components/EmailDetail", () => ({
  EmailDetail: ({
    emailId,
    actionCommand,
  }: {
    emailId: number | null;
    actionCommand?: { action: string; id: number } | null;
  }) => {
    React.useEffect(() => {
      if (emailId !== null && actionCommand) {
        mockDetailCommands.executions.push(`${emailId}:${actionCommand.action}:${actionCommand.id}`);
      }
    }, [actionCommand, emailId]);

    return (
      <section aria-label="mock email detail">
        <span>email:{emailId ?? "none"}</span>
        <span>action:{actionCommand?.action ?? "none"}</span>
      </section>
    );
  },
}));

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
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

import Home from "./page";
import { setMobileWorkspaceView } from "@/lib/mobile-workspace";

function countText(haystack: string, needle: string) {
  return haystack.split(needle).length - 1;
}

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

describe("Home workspace action bridge", () => {
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
    mockEmailSelection.emailId = 42;
    mockDetailCommands.executions = [];
    localStorage.clear();
    window.history.replaceState(null, "", "/");
    Reflect.deleteProperty(window, "__naruonMobileWorkspace");
    vi.unstubAllGlobals();
  });

  it("asks users to choose an email before running a shell action", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });

    await act(async () => {
      window.dispatchEvent(new CustomEvent("naruon:header-action", { detail: { action: "reply-draft" } }));
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("먼저 메일을 선택하세요.");
    expect(container.textContent).toContain("action:none");
  });

  it("forwards shell actions to the selected email detail", async () => {
    localStorage.setItem("naruon_startup_view", "email");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });

    await act(async () => {
      container?.querySelector<HTMLButtonElement>("button")?.click();
    });
    await act(async () => {
      window.dispatchEvent(new CustomEvent("naruon:header-action", { detail: { action: "calendar-sync" } }));
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("email:42");
    expect(container.textContent).toContain("action:calendar-sync");
    expect(countText(container.textContent ?? "", "action:calendar-sync")).toBe(1);
    expect(mockDetailCommands.executions).toEqual(["42:calendar-sync:1"]);
    expect(container.textContent).not.toContain("먼저 메일을 선택하세요.");
  });

  it("does not replay a desktop shell action after a desktop-tablet-desktop resize", async () => {
    localStorage.setItem("naruon_startup_view", "email");
    const mobileListeners = new Set<(event: MediaQueryListEvent) => void>();
    const tabletListeners = new Set<(event: MediaQueryListEvent) => void>();
    let mobileMatches = false;
    let tabletMatches = false;
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      get matches() {
        if (query.includes("max-width: 1023px")) return mobileMatches;
        return query.includes("min-width: 1024px") ? tabletMatches : false;
      },
      media: query,
      addEventListener: (_event: "change", listener: (event: MediaQueryListEvent) => void) => {
        if (query.includes("max-width: 1023px")) mobileListeners.add(listener);
        if (query.includes("min-width: 1024px")) tabletListeners.add(listener);
      },
      removeEventListener: (_event: "change", listener: (event: MediaQueryListEvent) => void) => {
        mobileListeners.delete(listener);
        tabletListeners.delete(listener);
      },
    })));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await act(async () => {
      container?.querySelector<HTMLButtonElement>("button")?.click();
    });
    await act(async () => {
      window.dispatchEvent(new CustomEvent("naruon:header-action", { detail: { action: "reply-draft" } }));
    });
    await flushAsyncWork();

    expect(mockDetailCommands.executions).toEqual(["42:reply-draft:1"]);

    await act(async () => {
      mobileMatches = true;
      mobileListeners.forEach((listener) => listener({ matches: true } as MediaQueryListEvent));
    });
    await flushAsyncWork();

    expect(mockDetailCommands.executions).toEqual(["42:reply-draft:1"]);

    await act(async () => {
      mobileMatches = false;
      mobileListeners.forEach((listener) => listener({ matches: false } as MediaQueryListEvent));
    });
    await flushAsyncWork();

    expect(mockDetailCommands.executions).toEqual(["42:reply-draft:1"]);
    expect(countText(container.textContent ?? "", "email:42")).toBe(1);

    await act(async () => {
      tabletMatches = true;
      tabletListeners.forEach((listener) => listener({ matches: true } as MediaQueryListEvent));
    });
    await flushAsyncWork();

    expect(mockDetailCommands.executions).toEqual(["42:reply-draft:1"]);

    await act(async () => {
      tabletMatches = false;
      tabletListeners.forEach((listener) => listener({ matches: false } as MediaQueryListEvent));
    });
    await flushAsyncWork();

    expect(mockDetailCommands.executions).toEqual(["42:reply-draft:1"]);
  });

  it("unmounts the mobile detail pane after returning from mobile to desktop", async () => {
    localStorage.setItem("naruon_startup_view", "email");
    const mobileListeners = new Set<(event: MediaQueryListEvent) => void>();
    let mobileMatches = true;
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      get matches() {
        return query.includes("max-width: 1023px") ? mobileMatches : false;
      },
      media: query,
      addEventListener: (_event: "change", listener: (event: MediaQueryListEvent) => void) => {
        if (query.includes("max-width: 1023px")) mobileListeners.add(listener);
      },
      removeEventListener: (_event: "change", listener: (event: MediaQueryListEvent) => void) => {
        mobileListeners.delete(listener);
      },
    })));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await act(async () => {
      container?.querySelector<HTMLButtonElement>("button")?.click();
    });
    await act(async () => {
      window.dispatchEvent(new CustomEvent("naruon:header-action", { detail: { action: "reply-draft" } }));
    });
    await flushAsyncWork();

    expect(countText(container.textContent ?? "", "email:42")).toBe(1);
    expect(mockDetailCommands.executions).toEqual(["42:reply-draft:1"]);

    await act(async () => {
      mobileMatches = false;
      mobileListeners.forEach((listener) => listener({ matches: false } as MediaQueryListEvent));
    });
    await flushAsyncWork();

    expect(countText(container.textContent ?? "", "email:42")).toBe(1);
    expect(mockDetailCommands.executions).toEqual(["42:reply-draft:1"]);

    await act(async () => {
      mobileMatches = true;
      mobileListeners.forEach((listener) => listener({ matches: true } as MediaQueryListEvent));
    });
    await flushAsyncWork();

    expect(mockDetailCommands.executions).toEqual(["42:reply-draft:1"]);
  });

  it("does not replay a stale mobile shell action after returning to the inbox", async () => {
    const listeners = new Set<(event: MediaQueryListEvent) => void>();
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: (_event: "change", listener: (event: MediaQueryListEvent) => void) => listeners.add(listener),
      removeEventListener: (_event: "change", listener: (event: MediaQueryListEvent) => void) => listeners.delete(listener),
    })));

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });

    await act(async () => {
      container?.querySelector<HTMLButtonElement>("button")?.click();
    });
    await act(async () => {
      window.dispatchEvent(new CustomEvent("naruon:header-action", { detail: { action: "reply-draft" } }));
    });
    await flushAsyncWork();

    expect(countText(container.textContent ?? "", "action:reply-draft")).toBe(1);

    await act(async () => {
      Array.from(container?.querySelectorAll<HTMLButtonElement>("button") ?? [])
        .find((button) => button.textContent?.includes("목록으로"))
        ?.click();
    });
    mockEmailSelection.emailId = 43;
    await act(async () => {
      container?.querySelector<HTMLButtonElement>("button")?.click();
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("email:43");
    expect(container.textContent).toContain("action:none");
    expect(container.textContent).not.toContain("action:reply-draft");
  });

  it("defaults to the Today dashboard when no startup preference is saved", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("김나루님");
    expect(container.textContent).toContain("메일함 바로가기");
    expect(window.location.hash).toBe("");
  });

  it("includes a tablet workspace with a collapsed context panel", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: query.includes("min-width: 1024px"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    expect(container.querySelector('[aria-label="태블릿 메일 작업공간"]')).not.toBeNull();
    expect(container.querySelector('details[aria-label="태블릿 관계 맥락"]')?.textContent).toContain("태블릿 맥락 패널");
    expect(container.textContent).toContain("관계 맥락은 필요할 때 펼쳐서 확인합니다.");
  });

  it("opens the saved calendar startup view on mobile without needing a hash", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    localStorage.setItem("naruon_startup_view", "calendar");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    expect(container.querySelector('#mobile-calendar')?.className).toContain("flex");
    expect(container.textContent).toContain("일정 반영 대기");
    expect(window.location.hash).toBe("");
  });

  it("shows the saved dashboard startup view until users switch back to email", async () => {
    localStorage.setItem("naruon_startup_view", "dashboard");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("김나루님");
    expect(container.textContent).toContain("메일함 바로가기");

    await act(async () => {
      Array.from(container?.querySelectorAll<HTMLButtonElement>("button") ?? [])
        .find((button) => button.textContent?.includes("메일함 바로가기"))
        ?.click();
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("메일 선택");
    expect(container.textContent).toContain("email:none");
  });

  it("backs the desktop startup dashboard with live mail reply and task data", async () => {
    localStorage.setItem("naruon_startup_view", "dashboard");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/emails/pending-replies?limit=3")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [
              { id: 102, subject: "출시 리뷰 일정 조율", sender: "pm@example.com", date: "2026-05-17T10:00:00Z", snippet: "일정 반영 후보" },
            ],
          }),
        });
      }
      if (url.endsWith("/api/emails")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            emails: [
              { id: 101, subject: "고객 계약 승인 대기", sender: "legal@example.com", date: "2026-05-17T09:00:00Z", snippet: "오늘 승인해야 하는 계약 검토 요청", unread: true },
            ],
          }),
        });
      }
      if (url.endsWith("/api/tasks")) {
        return Promise.resolve({
          ok: true,
          json: async () => ([
            { id: "task_public_1", title: "계약 승인 확인", status: "open", priority: "high", created_at: "2026-05-17T09:00:00Z", updated_at: "2026-05-17T09:00:00Z" },
          ]),
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await waitForCondition(() => container?.textContent?.includes("계약 승인 확인") ?? false);

    expect(container.textContent).toContain("고객 계약 승인 대기");
    expect(container.textContent).toContain("출시 리뷰 일정 조율");
    expect(container.textContent).toContain("계약 승인 확인");
    expect(fetch).toHaveBeenCalledWith("/api/emails", expect.any(Object));
    expect(fetch).toHaveBeenCalledWith("/api/emails/pending-replies?limit=3", expect.any(Object));
    expect(fetch).toHaveBeenCalledWith("/api/tasks", expect.any(Object));
  });

  it("backs the desktop calendar startup view with live calendar candidates", async () => {
    localStorage.setItem("naruon_startup_view", "calendar");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/search")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            results: [
              { id: 201, subject: "엔터프라이즈 데모 일정", sender: "sales@example.com", date: "2026-05-18T11:00:00Z", snippet: "다음 주 데모 일정 조율" },
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
      root?.render(<Home />);
    });
    await waitForCondition(() => container?.textContent?.includes("엔터프라이즈 데모 일정") ?? false);

    expect(container.textContent).toContain("엔터프라이즈 데모 일정");
    expect(container.textContent).not.toContain("디자인 리뷰 후속 조치");
    expect(fetch).toHaveBeenCalledWith("/api/search", expect.objectContaining({ method: "POST" }));
  });

  it("shows an unavailable dashboard state for malformed API payloads", async () => {
    localStorage.setItem("naruon_startup_view", "dashboard");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => ({ results: [] }),
    })));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await waitForCondition(() => Boolean(container?.querySelector('[role="alert"][aria-label="대시보드 데이터 상태"]')));

    expect(container.textContent).toContain("업무 현황을 모두 불러오지 못했습니다.");
    expect(container.textContent).not.toContain("수신된 메일이 없습니다.");
    expect(container.textContent).not.toContain("답변 대기 중인 보낸 메일이 없습니다.");
    expect(container.textContent).not.toContain("대기 작업이 없습니다.");
  });

  it("shows desktop calendar empty and error states from the search API", async () => {
    localStorage.setItem("naruon_startup_view", "calendar");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => ({ results: [] }),
    })));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await waitForCondition(() => container?.textContent?.includes("일정 후보가 없습니다.") ?? false);

    expect(container.textContent).toContain("일정 후보가 없습니다.");

    act(() => root?.unmount());
    container.textContent = "";
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: async () => ({}),
    })));
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await waitForCondition(() => container?.textContent?.includes("일정 후보를 불러오지 못했습니다.") ?? false);

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("일정 후보를 불러오지 못했습니다.");
  });

  it("lets a mobile hash deep link override a saved dashboard startup view", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    localStorage.setItem("naruon_startup_view", "dashboard");
    window.history.replaceState(null, "", "/#mobile-calendar");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    expect(container.querySelector('#mobile-calendar')?.className).toContain("flex");
    expect(container.textContent).toContain("일정 반영 대기");
    expect(container.textContent).not.toContain("오늘의 실행 홈");
  });

  it("lets hashless mobile workspace events override a saved dashboard startup view", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    localStorage.setItem("naruon_startup_view", "dashboard");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("김나루님");

    await act(async () => {
      setMobileWorkspaceView("calendar", { updateHash: false });
    });
    await flushAsyncWork();

    expect(window.location.hash).toBe("");
    expect(container.querySelector('#mobile-calendar')?.className).toContain("flex");
    expect(container.textContent).toContain("일정 반영 대기");
    expect(container.textContent).not.toContain("오늘의 실행 홈");
  });

  it("ignores malformed hashless mobile workspace events for dashboard overrides", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    localStorage.setItem("naruon_startup_view", "dashboard");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();
    expect(container.textContent).toContain("김나루님");

    await act(async () => {
      window.dispatchEvent(new CustomEvent("naruon:mobile-workspace", { detail: {} }));
    });
    await flushAsyncWork();

    expect(window.location.hash).toBe("");
    expect(container.textContent).toContain("김나루님");
    expect(container.querySelector('#mobile-calendar')?.className).toContain("hidden");
  });

  it("does not fetch desktop dashboard data before a mobile hash override is applied", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    localStorage.setItem("naruon_startup_view", "dashboard");
    window.history.replaceState(null, "", "/#mobile-calendar");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => ({ results: [] }),
    })));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    const searchQueries = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls
      .filter(([input]) => String(input).endsWith("/api/search"))
      .map(([, init]) => String(init?.body ?? ""));
    expect(searchQueries.some((body) => body.includes("판단 대기"))).toBe(false);
  });

  it("keeps the dashboard visible when unrelated hash links change", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    localStorage.setItem("naruon_startup_view", "dashboard");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();
    expect(container.textContent).toContain("김나루님");

    await act(async () => {
      window.history.replaceState(null, "", "/#main-content");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("김나루님");
    expect(container.querySelector('#mobile-calendar')?.className).toContain("hidden");
  });

  it("restores the saved dashboard when a mobile hash is removed", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    localStorage.setItem("naruon_startup_view", "dashboard");
    window.history.replaceState(null, "", "/#mobile-calendar");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();
    expect(container.textContent).toContain("일정 반영 대기");

    await act(async () => {
      window.history.replaceState(null, "", "/");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("김나루님");
    expect(container.textContent).not.toContain("일정 반영 대기");
  });

  it("renders an API-backed loading state for the mobile search panel instead of placeholders", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
    window.history.replaceState(null, "", "/#mobile-search");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    expect(container.querySelector('#mobile-search')?.className).toContain("flex");
    expect(container.textContent).toContain("맥락 검색 결과를 불러오는 중입니다.");
    expect(fetch).toHaveBeenCalledWith("/api/search", expect.objectContaining({ method: "POST" }));
  });

  it("renders an API-backed loading state for the mobile calendar panel instead of static candidates", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true,
      media: "(max-width: 1023px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
    window.history.replaceState(null, "", "/#mobile-calendar");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<Home />);
    });
    await flushAsyncWork();

    expect(container.querySelector('#mobile-calendar')?.className).toContain("flex");
    expect(container.textContent).toContain("일정 후보를 불러오는 중입니다.");
    expect(container.textContent).not.toContain("디자인 리뷰 후속 조치");
    expect(fetch).toHaveBeenCalledWith("/api/search", expect.objectContaining({ method: "POST" }));
  });
});
