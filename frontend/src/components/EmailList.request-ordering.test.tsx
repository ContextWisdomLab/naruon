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

describe("EmailList request ordering", () => {
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

  it("keeps cleared inbox results when an older search completes later", async () => {
    let resolveSearch: ((value: ReturnType<typeof jsonResponse>) => void) | null = null;
    let resolveInboxRefresh: ((value: ReturnType<typeof jsonResponse>) => void) | null = null;
    let inboxCalls = 0;

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/search")) {
        return new Promise((resolve) => {
          resolveSearch = resolve;
        });
      }
      if (url.endsWith("/api/emails")) {
        inboxCalls += 1;
        if (inboxCalls === 1) {
          return Promise.resolve(jsonResponse({ emails: [] }));
        }
        return new Promise((resolve) => {
          resolveInboxRefresh = resolve;
        });
      }
      throw new Error(`Unexpected request: ${url}`);
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
    expect(input).not.toBeNull();
    expect(form).not.toBeNull();

    await act(async () => {
      setInputValue(input as HTMLInputElement, "계약");
    });
    await act(async () => {
      form?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(resolveSearch).not.toBeNull();

    const clearButton = container.querySelector<HTMLButtonElement>('button[aria-label="맥락 검색어 지우기"]');
    expect(clearButton).not.toBeNull();

    await act(async () => {
      clearButton?.click();
    });

    expect(resolveInboxRefresh).not.toBeNull();

    await act(async () => {
      resolveInboxRefresh?.(jsonResponse({
        emails: [
          {
            id: 41,
            sender: "운영팀",
            subject: "최신 받은편지함",
            snippet: "검색 해제 뒤 표시해야 하는 받은 메일입니다.",
          },
        ],
      }));
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("최신 받은편지함");

    await act(async () => {
      resolveSearch?.(jsonResponse({
        results: [
          {
            id: 99,
            sender: "검색 인덱스",
            subject: "늦게 도착한 검색 결과",
            snippet: "더 오래된 검색 요청의 응답입니다.",
          },
        ],
      }));
    });
    await flushAsyncWork();

    expect(input?.value).toBe("");
    expect(container.textContent).toContain("최신 받은편지함");
    expect(container.textContent).not.toContain("늦게 도착한 검색 결과");
  });
});
