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

import { customerFacingRelationshipText, SearchLayout } from "./SearchLayout";
import {
  clearRecordedProductEvents,
  getRecordedProductEvents,
} from "@/lib/product-events";

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

function setInputValue(input: HTMLInputElement, value: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  )?.set;
  valueSetter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("SearchLayout product events", () => {
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
    clearRecordedProductEvents();
  });

  it("records context search submit, result open, and result action events without raw query text", async () => {
    const randomUUID = vi.fn(
      () =>
        "11111111-2222-4333-8444-555555555555" as `${string}-${string}-${string}-${string}-${string}`,
    );
    vi.stubGlobal("crypto", {
      randomUUID,
      getRandomValues: <T extends ArrayBufferView | null>(array: T) => array,
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/search")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { query?: string };
        const isContractSearch = body.query === "계약";
        return Promise.resolve(jsonResponse({
          results: [{
            id: isContractSearch ? 202 : 101,
            source_message_id: isContractSearch ? "<contract-source@example.com>" : "<launch-source@example.com>",
            subject: isContractSearch ? "계약 검토 결과" : "런칭 캠페인 결과",
            sender: "pm@example.com",
            date: "2026-05-20T09:00:00Z",
            snippet: "검색 결과에서 관계 캡처 액션을 실행할 수 있습니다.",
            thread_id: isContractSearch ? "thread-contract" : "thread-launch",
            reply_count: 2,
            score: 0.93,
          }],
        }));
      }
      if (url.includes("/api/ontology/relationships?")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.endsWith("/api/ontology/relationships/capture-source")) {
        return Promise.resolve(jsonResponse({
          sender_email: "pm@example.com",
          parent_sender_email: null,
          source_message_id: "<contract-source@example.com>",
          source_thread_id: "thread-contract",
          relationship_type: "sender_context",
          confidence_score: 0.91,
          next_action: "계약 검토 담당자를 확인합니다.",
          action_reason: "검색 결과 원본 메시지의 후속 조치입니다.",
        }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchLayout />);
    });
    await waitForCondition(() => container?.textContent?.includes("런칭 캠페인 결과") ?? false);

    expect(getRecordedProductEvents().some((event) =>
      event.name === "context_search_result_opened" &&
      event.payload.result_id === 101,
    )).toBe(true);

    const input = container.querySelector<HTMLInputElement>("#search-input");
    const form = input?.closest("form");
    expect(input).not.toBeNull();
    expect(form).not.toBeNull();

    await act(async () => {
      setInputValue(input as HTMLInputElement, "계약");
      form?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await waitForCondition(() => container?.textContent?.includes("계약 검토 결과") ?? false);

    expect(getRecordedProductEvents().some((event) =>
      event.name === "context_search_submitted" &&
      event.payload.surface === "context_search" &&
      event.payload.query_length_bucket === "1_20" &&
      event.payload.search_session_id ===
        "context_search_session_11111111-2222-4333-8444-555555555555",
    )).toBe(true);
    expect(getRecordedProductEvents().some((event) =>
      event.name === "context_search_result_opened" &&
      event.payload.result_id === 202 &&
      event.payload.rank_bucket === "top_1",
    )).toBe(true);

    await waitForCondition(() => Array.from(container?.querySelectorAll<HTMLButtonElement>("button") ?? []).some(
      (button) => button.textContent?.includes("발신자 관계 캡처") && !button.disabled,
    ));
    const captureButton = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent?.includes("발신자 관계 캡처") && !button.disabled,
    );
    expect(captureButton?.textContent).toContain("발신자 관계 캡처");

    await act(async () => {
      captureButton?.click();
    });
    await waitForCondition(() => fetchMock.mock.calls.some(([input]) =>
      String(input).endsWith("/api/ontology/relationships/capture-source"),
    ));
    await waitForCondition(() => getRecordedProductEvents().some((event) => event.name === "context_search_result_action_created"));

    expect(container.textContent).toContain("발신자 맥락");
    expect(container.textContent).toContain("다음 행동");
    expect(container.textContent).not.toContain("sender_context");
    expect(container.textContent).not.toContain("thread-contract");
    expect(container.textContent).not.toContain("<contract-source@example.com>");

    expect(getRecordedProductEvents().some((event) =>
      event.name === "context_search_result_action_created" &&
      event.payload.result_id === 202 &&
      event.payload.action_type === "relation_capture" &&
      event.payload.source_backlink_present === true,
    )).toBe(true);
    expect(JSON.stringify(getRecordedProductEvents())).not.toContain("계약");
  });

  it.each([
    ["summarize_then_archive", "요약 후 보관합니다."],
    ["track_reply_and_tasks", "답장과 후속 작업을 확인합니다."],
    ["prepare_response_draft", "답장 초안을 준비합니다."],
    ["classify_sender", "발신자 관계를 확인합니다."],
  ])("maps production relationship action %s to customer copy", (nextAction, expectedCopy) => {
    expect(customerFacingRelationshipText(nextAction, "후속 작업을 확인합니다.")).toBe(
      expectedCopy,
    );
  });

  it.each(["reply.follow-up", "reply/follow_up", "reply follow_up", "회신_대기", ""])(
    "fails closed for non-catalog relationship action %s",
    (nextAction) => {
    expect(customerFacingRelationshipText(nextAction, "후속 작업을 확인합니다.")).toBe(
      "후속 작업을 확인합니다.",
    );
    },
  );

  it("shows customer-facing copy when relationship loading fails", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/search")) {
        return Promise.resolve(jsonResponse({ results: [{
          id: 1,
          source_message_id: "source@example.com",
          subject: "Search result",
          sender: "pm@example.com",
          date: "2026-05-20T09:00:00Z",
          snippet: "Result",
          thread_id: "thread-1",
          reply_count: 0,
          score: 0.9,
        }] }));
      }
      if (url.includes("/api/ontology/relationships?")) {
        return Promise.reject(new Error("relationship service unavailable"));
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    }));

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<SearchLayout />);
    });
    await waitForCondition(() =>
      container?.textContent?.includes("발신자 관계를 불러오지 못했습니다.") ?? false,
    );
    expect(container.textContent).not.toContain("DAG");
  });
});
