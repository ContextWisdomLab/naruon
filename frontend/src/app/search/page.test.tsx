/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("lucide-react", () => ({
  Search: () => <svg aria-hidden="true" />,
  Mail: () => <svg aria-hidden="true" />,
  CalendarDays: () => <svg aria-hidden="true" />,
  FileText: () => <svg aria-hidden="true" />,
  Sparkles: () => <svg aria-hidden="true" />,
  UserRound: () => <svg aria-hidden="true" />,
  Network: () => <svg aria-hidden="true" />,
  Clock: () => <svg aria-hidden="true" />,
  CheckCircle2: () => <svg aria-hidden="true" />,
  AlertCircle: () => <svg aria-hidden="true" />,
  CornerDownRight: () => <svg aria-hidden="true" />,
  Loader2: () => <svg aria-hidden="true" className="lucide-loader-2" />,
  X: () => <svg aria-hidden="true" />,
}));

vi.mock("vis-network", () => ({
  Network: vi.fn(function MockNetwork() {
    return { destroy: vi.fn(), fit: vi.fn() };
  }),
}));

import SearchPage from "./page";

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: async () => body,
  };
}

async function flushAsyncWork() {
  for (let index = 0; index < 6; index += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

function lowerCaseHeaders(headers: HeadersInit | undefined) {
  if (!headers) return {};
  if (headers instanceof Headers) {
    return Object.fromEntries(
      Array.from(headers.entries()).map(([key, value]) => [
        key.toLowerCase(),
        value,
      ]),
    );
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(
      headers.map(([key, value]) => [key.toLowerCase(), value]),
    );
  }
  return Object.fromEntries(
    Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]),
  );
}

function clickButton(container: HTMLElement, label: string) {
  const button = Array.from(container.querySelectorAll("button")).find((node) =>
    node.textContent?.includes(label),
  );
  expect(button).not.toBeUndefined();
  act(() => {
    button?.click();
  });
}

describe("SearchPage", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    root = null;
    container?.remove();
    container = null;
    window.localStorage.clear();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("renders API-backed search results with reply tracking and signed session headers", async () => {
    const fetchMock = vi.fn((...args: [RequestInfo | URL, RequestInit?]) => {
      const [input] = args;
      const url = String(input);
      if (url.endsWith("/api/search")) {
        return Promise.resolve(
          jsonResponse({
            results: [
              {
                id: 7,
                source_message_id: "<q2@example.com>",
                subject: "Q2 출시 계획 및 우선순위 조정",
                sender: "김지현 PM",
                date: "2026-05-11T09:30:00Z",
                snippet:
                  "Q2 출시 일정과 마케팅 계획을 우선순위 기준으로 재정렬했습니다.",
                thread_id: "thread-q2",
                reply_count: 3,
                score: 0.87,
              },
            ],
          }),
        );
      }
      if (url.includes("/api/ontology/relationships")) {
        return Promise.resolve(
          jsonResponse([
            {
              sender_email: "jihyun@naruon.ai",
              parent_sender_email: "user@naruon.ai",
              source_message_id: "<q2@example.com>",
              source_thread_id: "thread-q2",
              relationship_type: "Colleague",
              confidence_score: 0.85,
              next_action: "track_reply_and_tasks",
              action_reason:
                "Same-domain sender; preserve reply and task follow-up.",
            },
          ]),
        );
      }
      if (url.endsWith("/api/network/graph")) {
        return Promise.resolve(
          jsonResponse({
            nodes: [{ id: "sender-1", label: "김지현 PM", title: "PM" }],
            edges: [
              {
                source: "sender-1",
                target: "sender-1",
                weight: 1,
                title: "관련 메일",
              },
            ],
          }),
        );
      }
      return Promise.resolve(jsonResponse({}, false, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchPage />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("Q2 출시 계획 및 우선순위 조정");
    expect(container.textContent).toContain("메일 흐름 연결됨");
    expect(container.textContent).not.toContain("thread-q2");
    expect(container.textContent).toContain("답장 3건");
    expect(container.textContent).toContain("신뢰도 87%");
    expect(container.textContent).toContain("증거 바인딩");
    expect(container.textContent).toContain("맥락 정보");
    expect(container.textContent).toContain("메일 열기");
    expect(container.textContent).toContain("관계 맥락과 타임라인");
    expect(container.textContent).toContain("발신자 관계");
    expect(container.textContent).toContain("답장과 후속 작업을 확인합니다.");
    expect(container.textContent).not.toContain("track_reply_and_tasks");
    expect(container.textContent).not.toContain("<q2@example.com>");
    expect(container.querySelector("#search-detail-tab-context")?.getAttribute("aria-controls")).toBe("search-detail-panel-context");
    expect(container.querySelector("#search-detail-panel-context")?.getAttribute("role")).toBe("tabpanel");

    clickButton(container, "관계 원본");
    expect(container.querySelector("#search-detail-panel-source")?.getAttribute("aria-labelledby")).toBe("search-detail-tab-source");
    expect(container.textContent).toContain("관계 상태");
    expect(container.textContent).toContain("1개 관계 연결");

    clickButton(container, "판단 보조");
    expect(container.querySelector("#search-detail-panel-assist")?.getAttribute("aria-labelledby")).toBe("search-detail-tab-assist");
    expect(container.textContent).toContain("외부 실행은 사용자가 메일, 일정, 관계 캡처 액션을 명시적으로 선택할 때만 진행됩니다.");

    const searchCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/search"),
    );
    expect(searchCall).toBeDefined();
    expect(searchCall?.[1]?.method).toBe("POST");
    expect(searchCall?.[1]?.body).toBe(
      JSON.stringify({ query: "런칭 캠페인", limit: 8 }),
    );
    const headers = lowerCaseHeaders(searchCall?.[1]?.headers);
    expect(searchCall?.[1]?.credentials).toBe("same-origin");
    expect(headers.authorization).toBeUndefined();
    for (const headerName of [
      "x-user-id",
      "x-organization-id",
      "x-group-id",
      "x-group-ids",
      "x-user-role",
      "x-dev-auth-token",
    ]) {
      expect(headers[headerName]).toBeUndefined();
    }

    const ontologyCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes("/api/ontology/relationships"),
    );
    expect(ontologyCall).toBeDefined();
    expect(String(ontologyCall?.[0])).toContain(
      "source_message_id=%3Cq2%40example.com%3E",
    );
    expect(String(ontologyCall?.[0])).toContain("source_thread_id=thread-q2");
    const ontologyHeaders = lowerCaseHeaders(ontologyCall?.[1]?.headers);
    expect(ontologyCall?.[1]?.credentials).toBe("same-origin");
    expect(ontologyHeaders.authorization).toBeUndefined();
    for (const headerName of [
      "x-user-id",
      "x-organization-id",
      "x-group-id",
      "x-group-ids",
      "x-user-role",
      "x-dev-auth-token",
    ]) {
      expect(ontologyHeaders[headerName]).toBeUndefined();
    }
  });

  it("renders search snippets as escaped text instead of executable HTML", async () => {
    const maliciousSnippet =
      '검토 필요 <img src=x onerror="window.__naruonSearchXss = true"><script>window.__naruonSearchXss = true</script>';
    const fetchMock = vi.fn((...args: [RequestInfo | URL, RequestInit?]) => {
      const [input] = args;
      const url = String(input);
      if (url.endsWith("/api/search")) {
        return Promise.resolve(
          jsonResponse({
            results: [
              {
                id: 17,
                source_message_id: "<xss@example.com>",
                subject: "HTML snippet boundary",
                sender: "보안 검토",
                date: "2026-05-11T09:30:00Z",
                snippet: maliciousSnippet,
                thread_id: "thread-xss",
                reply_count: 1,
                score: 0.91,
              },
            ],
          }),
        );
      }
      if (url.includes("/api/ontology/relationships")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.endsWith("/api/network/graph")) {
        return Promise.resolve(jsonResponse({ nodes: [], edges: [] }));
      }
      return Promise.resolve(jsonResponse({}, false, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchPage />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain(maliciousSnippet);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(
      (window as Window & { __naruonSearchXss?: boolean })
        .__naruonSearchXss,
    ).toBeUndefined();

    const searchCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/search"),
    );
    expect(searchCall).toBeDefined();
    const headers = lowerCaseHeaders(searchCall?.[1]?.headers);
    expect(searchCall?.[1]?.credentials).toBe("same-origin");
    expect(headers.authorization).toBeUndefined();
  });

  it("captures a source-backed sender DAG relationship through signed headers", async () => {
    const fetchMock = vi.fn((...args: [RequestInfo | URL, RequestInit?]) => {
      const [input] = args;
      const url = String(input);
      if (url.endsWith("/api/search")) {
        return Promise.resolve(
          jsonResponse({
            results: [
              {
                id: 8,
                source_message_id: "<capture@example.com>",
                subject: "관계 캡처 대상",
                sender: "박민재",
                date: "2026-05-29T09:30:00Z",
                snippet: "같은 thread에서 발신자 관계를 캡처합니다.",
                thread_id: "thread-capture",
                reply_count: 1,
                score: 0.72,
              },
            ],
          }),
        );
      }
      if (url.includes("/api/ontology/relationships/capture-source")) {
        return Promise.resolve(
          jsonResponse({
            sender_email: "minjae@naruon.ai",
            parent_sender_email: null,
            source_message_id: "<capture@example.com>",
            source_thread_id: "thread-capture",
            relationship_type: "Colleague",
            confidence_score: 0.85,
            next_action: "track_reply_and_tasks",
            action_reason:
              "Same-domain sender; preserve reply and task follow-up.",
          }),
        );
      }
      if (url.includes("/api/ontology/relationships")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.endsWith("/api/network/graph")) {
        return Promise.resolve(jsonResponse({ nodes: [], edges: [] }));
      }
      return Promise.resolve(jsonResponse({}, false, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchPage />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain(
      "이 맥락 검색 결과에 연결된 발신자 관계가 아직 없습니다.",
    );
    const captureButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("발신자 관계 캡처"),
    );
    expect(captureButton).toBeDefined();

    await act(async () => {
      captureButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();

    const captureCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes("/api/ontology/relationships/capture-source"),
    );
    expect(captureCall).toBeDefined();
    expect(captureCall?.[1]?.method).toBe("POST");
    expect(captureCall?.[1]?.body).toBe(
      JSON.stringify({ source_message_id: "<capture@example.com>" }),
    );
    const captureHeaders = lowerCaseHeaders(captureCall?.[1]?.headers);
    expect(captureCall?.[1]?.credentials).toBe("same-origin");
    expect(captureHeaders.authorization).toBeUndefined();
    for (const headerName of [
      "x-user-id",
      "x-organization-id",
      "x-group-id",
      "x-group-ids",
      "x-user-role",
      "x-dev-auth-token",
    ]) {
      expect(captureHeaders[headerName]).toBeUndefined();
    }
    expect(container.textContent).toContain("minjae@naruon.ai");
    expect(container.textContent).toContain("답장과 후속 작업을 확인합니다.");
    expect(container.textContent).toContain("업무 관계");
    expect(container.textContent).not.toContain("track_reply_and_tasks");
    expect(container.textContent).not.toContain("<capture@example.com>");
    expect(container.textContent).not.toContain("thread-capture");
  });

  it("renders a fail-closed error state when the search API rejects the query", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/search"))
          return Promise.resolve(
            jsonResponse(
              { detail: "OpenAI API key not configured" },
              false,
              400,
            ),
          );
        if (url.includes("/api/ontology/relationships"))
          return Promise.resolve(jsonResponse([]));
        if (url.endsWith("/api/network/graph"))
          return Promise.resolve(jsonResponse({ nodes: [], edges: [] }));
        return Promise.resolve(jsonResponse({}, false, 404));
      }),
    );
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchPage />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("맥락 검색 결과를 불러오지 못했습니다.");
  });

  it("clears the query with the custom button while keeping focus on the searchbox", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/search"))
          return Promise.resolve(jsonResponse({ results: [] }));
        if (url.includes("/api/ontology/relationships"))
          return Promise.resolve(jsonResponse([]));
        if (url.endsWith("/api/network/graph"))
          return Promise.resolve(jsonResponse({ nodes: [], edges: [] }));
        return Promise.resolve(jsonResponse({}, false, 404));
      }),
    );
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchPage />);
    });
    await flushAsyncWork();

    const input = container.querySelector("#search-input") as HTMLInputElement | null;
    expect(input).not.toBeNull();
    expect(input?.type).toBe("search");
    expect(input?.getAttribute("inputmode")).toBe("search");
    expect(input?.getAttribute("role")).toBe("searchbox");
    expect(
      container.querySelector('button[aria-label="맥락 검색어 지우기"]'),
    ).not.toBeNull();

    await act(async () => {
      container!
        .querySelector('button[aria-label="맥락 검색어 지우기"]')
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(input?.value).toBe("");
    expect(document.activeElement).toBe(input);
    expect(
      container.querySelector('button[aria-label="맥락 검색어 지우기"]'),
    ).toBeNull();

    await act(async () => {
      input?.focus();
      if (input) {
        const valueSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          "value",
        )?.set;
        valueSetter?.call(input, "새 맥락 검색어");
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });

    expect(input?.value).toBe("새 맥락 검색어");
    expect(
      container.querySelector('button[aria-label="맥락 검색어 지우기"]'),
    ).not.toBeNull();
  });

  it("renders the grounded AI answer card with citations and hides it when the endpoint is unavailable", async () => {
    const fetchMock = vi.fn((...args: [RequestInfo | URL, RequestInit?]) => {
      const [input] = args;
      const url = String(input);
      if (url.endsWith("/api/search")) {
        return Promise.resolve(
          jsonResponse({
            results: [
              {
                id: 7,
                source_message_id: "<q2@example.com>",
                subject: "Q2 출시 계획 및 우선순위 조정",
                sender: "김지현 PM",
                date: "2026-05-11T09:30:00Z",
                snippet: "Q2 일정 종합",
                thread_id: "thread-q2",
                reply_count: 3,
                score: 0.87,
              },
            ],
          }),
        );
      }
      if (url.endsWith("/api/search/answer")) {
        return Promise.resolve(
          jsonResponse({
            answer: "Q2 출시는 5월 셋째 주로 조정되었습니다.",
            citations: [
              {
                email_id: 7,
                subject: "Q2 출시 계획 및 우선순위 조정",
                sender: "김지현 PM",
                snippet: "Q2 일정 종합",
              },
            ],
            provenance: "OpenAI (gpt-test)",
          }),
        );
      }
      if (url.includes("/api/ontology/relationships")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.endsWith("/api/network/graph")) {
        return Promise.resolve(jsonResponse({ nodes: [], edges: [] }));
      }
      return Promise.resolve(jsonResponse({}, false, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchPage />);
    });
    await flushAsyncWork();

    // Answer card rendered from /api/search/answer with validated citations.
    const card = container.querySelector('[data-testid="grounded-answer-card"]');
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain("Q2 출시는 5월 셋째 주로 조정되었습니다.");
    expect(card?.textContent).toContain("근거: Q2 출시 계획 및 우선순위 조정");
    expect(card?.textContent).toContain("OpenAI (gpt-test)");

    const answerCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/search/answer"),
    );
    expect(answerCall?.[1]?.method).toBe("POST");
    expect(answerCall?.[1]?.body).toBe(
      JSON.stringify({ query: "런칭 캠페인", limit: 5 }),
    );
  });

});
