/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/dynamic", () => ({
  default: () => function MockDynamic() {
    return <div>mock graph</div>;
  },
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("lucide-react", () => ({
  AlertCircle: () => <svg aria-hidden="true" />,
  CalendarDays: () => <svg aria-hidden="true" />,
  CheckCircle2: () => <svg aria-hidden="true" />,
  Clock: () => <svg aria-hidden="true" />,
  CornerDownRight: () => <svg aria-hidden="true" />,
  FileText: () => <svg aria-hidden="true" />,
  Loader2: () => <svg aria-hidden="true" />,
  Mail: () => <svg aria-hidden="true" />,
  Network: () => <svg aria-hidden="true" />,
  Search: () => <svg aria-hidden="true" />,
  Sparkles: () => <svg aria-hidden="true" />,
  X: () => <svg aria-hidden="true" />,
}));

import { SearchLayout } from "./SearchLayout";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

async function flushAsyncWork() {
  for (let index = 0; index < 5; index += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

async function waitForCondition(condition: () => boolean) {
  for (let index = 0; index < 20; index += 1) {
    if (condition()) return;
    await flushAsyncWork();
  }
  throw new Error("waitForCondition timed out after 20 attempts");
}

function searchResult() {
  return {
    id: 101,
    source_message_id: "<launch-source@example.com>",
    subject: "런칭 캠페인 결과",
    sender: "pm@example.com",
    date: "2026-05-20T09:00:00Z",
    snippet: "검색 결과에서 관계 캡처 액션을 실행할 수 있습니다.",
    thread_id: "thread-launch",
    reply_count: 2,
    score: 0.93,
  };
}

describe("SearchLayout live-region semantics", () => {
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

  it("announces an empty search result set as a polite status", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/search")) return Promise.resolve(jsonResponse({ results: [] }));
      if (url.endsWith("/api/search/answer")) return Promise.resolve(jsonResponse({ answer: null }));
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchLayout />);
    });
    await waitForCondition(() => container?.textContent?.includes("맥락 검색 결과가 없습니다.") ?? false);

    const emptyResultStatus = Array.from(container.querySelectorAll<HTMLElement>("[role='status']")).find(
      (node) => node.textContent?.includes("맥락 검색 결과가 없습니다."),
    );
    expect(emptyResultStatus).not.toBeUndefined();
    expect(emptyResultStatus?.getAttribute("aria-live")).toBe("polite");
  });

  it("announces the empty sender relationship message without wrapping its action button in a status region", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/search")) return Promise.resolve(jsonResponse({ results: [searchResult()] }));
      if (url.includes("/api/ontology/relationships?")) return Promise.resolve(jsonResponse([]));
      if (url.endsWith("/api/search/answer")) return Promise.resolve(jsonResponse({ answer: null }));
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchLayout />);
    });
    await waitForCondition(() => container?.textContent?.includes("발신자 관계 캡처") ?? false);

    const emptyRelationshipStatus = Array.from(container.querySelectorAll<HTMLElement>("[role='status']")).find(
      (node) => node.textContent?.includes("이 맥락 검색 결과에 연결된 발신자 관계가 아직 없습니다."),
    );
    expect(emptyRelationshipStatus).not.toBeUndefined();
    expect(emptyRelationshipStatus?.querySelector("button, a, input, select, textarea")).toBeNull();
  });

  it("announces relationship capture failure as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/search")) return Promise.resolve(jsonResponse({ results: [searchResult()] }));
      if (url.includes("/api/ontology/relationships?")) return Promise.resolve(jsonResponse([]));
      if (url.endsWith("/api/search/answer")) return Promise.resolve(jsonResponse({ answer: null }));
      if (url.endsWith("/api/ontology/relationships/capture-source")) {
        return Promise.resolve(new Response(JSON.stringify({ error_code: "capture_failed" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchLayout />);
    });
    await waitForCondition(() => container?.textContent?.includes("발신자 관계 캡처") ?? false);

    const captureButton = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent?.includes("발신자 관계 캡처"),
    );
    expect(captureButton).not.toBeUndefined();

    await act(async () => {
      captureButton?.click();
    });
    await waitForCondition(() => container?.textContent?.includes("발신자 관계 캡처에 실패했습니다.") ?? false);

    const captureAlert = Array.from(container.querySelectorAll<HTMLElement>("[role='alert']")).find(
      (node) => node.textContent?.includes("발신자 관계 캡처에 실패했습니다."),
    );
    expect(captureAlert).not.toBeUndefined();
  });
});