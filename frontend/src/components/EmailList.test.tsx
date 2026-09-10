/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EmailList } from "./EmailList";

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

function setInputValue(input: HTMLInputElement, value: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  )?.set;
  valueSetter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("EmailList", () => {
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

  it("renders the branded dense inbox and selected thread state", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          emails: [
            {
              id: 7,
              sender: "김지현 PM",
              subject: null,
              date: "2026-05-11T09:30:00Z",
              snippet: "Q2 출시 계획과 우선순위 조정 요청입니다.",
              unread: true,
              reply_count: 3,
            },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<EmailList onSelectEmail={vi.fn()} selectedEmailId={7} />);
    });
    await flushAsyncWork();

    const selectedThread = container.querySelector('button[aria-current="true"]');

    expect(fetchMock).toHaveBeenCalledWith("/api/emails", expect.any(Object));
    expect(container.textContent).toContain("받은편지함");
    expect(container.textContent).toContain("맥락 종합");
    expect(container.textContent).toContain("실행 항목");
    expect(container.textContent).not.toContain("오늘의 판단 포인트·Q2 출시 계획 및 우선순위 조정");
    expect(container.textContent).toContain("메일 데이터 기반으로 판단 포인트를 표시합니다");
    expect(container.textContent).toContain("(제목 없음)");
    expect(container.textContent).toContain("안 읽음");
    expect(container.textContent).toContain("3개 메시지");
    expect(selectedThread).not.toBeNull();
    expect(selectedThread?.className).toContain("min-h-20");
  });

  it("announces an empty inbox through exactly one polite status region", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ emails: [] })));
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<EmailList onSelectEmail={vi.fn()} selectedEmailId={null} />);
    });
    await flushAsyncWork();

    const emptyStatuses = Array.from(container.querySelectorAll<HTMLElement>('[role="status"]')).filter(
      (node) => node.textContent?.includes("받은 메일이 없습니다"),
    );
    expect(emptyStatuses).toHaveLength(1);
    expect(emptyStatuses[0]?.getAttribute("aria-live")).toBe("polite");
    expect(container.textContent).not.toContain("맥락 검색 결과가 없습니다");
  });

  it("uses the missing-title fallback for blank email subjects", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          emails: [
            {
              id: 9,
              sender: "운영팀",
              subject: "   ",
              date: "2026-05-11T09:30:00Z",
              snippet: "제목이 비어 있는 메일입니다.",
              unread: false,
              reply_count: 1,
            },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<EmailList onSelectEmail={vi.fn()} selectedEmailId={null} />);
    });
    await flushAsyncWork();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("(제목 없음)");
  });

  it("shows search loading feedback, distinguishes search-empty copy, and clears back to inbox results", async () => {
    let resolveSearch: ((value: ReturnType<typeof jsonResponse>) => void) | null = null;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/search")) {
        return new Promise((resolve) => {
          resolveSearch = resolve;
        });
      }
      return Promise.resolve(jsonResponse({ emails: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<EmailList onSelectEmail={vi.fn()} selectedEmailId={null} />);
    });
    await flushAsyncWork();

    const input = container.querySelector<HTMLInputElement>("#email-search");
    const form = input?.closest("form");
    const submitButton = form?.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(input).not.toBeNull();
    expect(form).not.toBeNull();
    expect(submitButton).not.toBeNull();
    expect(container.textContent).toContain("받은 메일이 없습니다");

    await act(async () => {
      setInputValue(input as HTMLInputElement, "계약");
    });
    expect(container.textContent).toContain("받은 메일이 없습니다");
    expect(container.textContent).not.toContain("맥락 검색 결과가 없습니다");

    const clearButton = container.querySelector<HTMLButtonElement>('button[aria-label="맥락 검색어 지우기"]');
    expect(clearButton).not.toBeNull();

    await act(async () => {
      form?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(submitButton?.disabled).toBe(true);
    expect(submitButton?.textContent).toContain("맥락 검색 중");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/search",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ query: "계약" }),
      }),
    );

    await act(async () => {
      resolveSearch?.(jsonResponse({ results: [] }));
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("맥락 검색 결과가 없습니다");
    expect(container.textContent).not.toContain("받은 메일이 없습니다");

    await act(async () => {
      clearButton?.click();
    });
    await flushAsyncWork();

    expect(input?.value).toBe("");
    expect(fetchMock).toHaveBeenLastCalledWith("/api/emails", expect.any(Object));
    expect(container.textContent).toContain("받은 메일이 없습니다");
  });

  it("renders sent mail reply tracking mode from the sent folder API", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          emails: [
            {
              id: 12,
              sender: "Seongho <user@naruon.ai>",
              subject: "계약 검토 확인 요청",
              date: "2026-05-11T09:30:00Z",
              snippet: "Please reply when the contract review is complete.",
              unread: false,
              reply_count: 1,
              requires_reply: true,
            },
            {
              id: 13,
              sender: "user@naruon.ai",
              subject: "나에게 보낸 회의 메모",
              date: "2026-05-11T10:30:00Z",
              snippet: "다음 회의 전까지 지식으로 정리할 메모입니다.",
              unread: false,
              reply_count: 1,
              is_self_sent: true,
            },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<EmailList onSelectEmail={vi.fn()} selectedEmailId={null} folder="sent" />);
    });
    await flushAsyncWork();

    expect(fetchMock).toHaveBeenCalledWith("/api/emails?folder=sent", expect.any(Object));
    expect(container.textContent).toContain("보낸 메일");
    expect(container.textContent).toContain("답변 추적");
    expect(container.textContent).toContain("응답 대기 중");
    expect(container.textContent).toContain("지식 정리");
  });

  it("renders untrusted email fields as plain display text without markup", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        jsonResponse({
          emails: [
            {
              id: 8,
              sender: '<img src=x onerror=alert(1)>',
              subject: '<script>alert(1)</script>',
              date: '2026-05-11T09:30:00Z',
              snippet: 'hello\u0000<script>alert(2)</script >',
              unread: false,
              reply_count: 1,
            },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<EmailList onSelectEmail={vi.fn()} selectedEmailId={null} />);
    });
    await flushAsyncWork();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("보낸 사람");
    expect(container.textContent).toContain("(제목 없음)");
    expect(container.textContent).toContain("hello�");
    expect(container.textContent).not.toContain("<img");
    expect(container.textContent).not.toContain("<script>");
    expect(container.textContent).not.toContain("alert(1)");
    expect(container.textContent).not.toContain("alert(2)");
  });
});