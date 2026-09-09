/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/ui/separator", () => ({
  Separator: () => <hr />,
}));

vi.mock("@/components/ui/avatar", () => ({
  Avatar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AvatarFallback: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("@/components/ui/checkbox", () => ({
  Checkbox: (props: React.InputHTMLAttributes<HTMLInputElement>) => (
    <input type="checkbox" {...props} />
  ),
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

vi.mock("@/components/ui/textarea", () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => (
    <textarea {...props} />
  ),
}));

vi.mock("@/components/ui/input", () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));

vi.mock("lucide-react", () => ({
  MessagesSquare: () => <svg aria-hidden="true" />,
  AlertCircle: () => <svg aria-hidden="true" />,
  ExternalLink: () => <svg aria-hidden="true" />,
  FileText: () => <svg aria-hidden="true" />,
  RefreshCw: () => <svg aria-hidden="true" />,
  Info: () => <svg aria-hidden="true" />,
  Loader2: () => <svg aria-hidden="true" />,
  X: () => <svg aria-hidden="true" />,
}));

import { EmailDetail } from "./EmailDetail";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

async function flushAsyncWork() {
  for (let index = 0; index < 6; index += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  if (!setter) throw new Error("HTMLInputElement value setter unavailable");
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function hiddenReasonUtility(className: string) {
  return className.split(/\s+/).find((token) => {
    const utility = token.slice(token.lastIndexOf(":") + 1).replace(/^!/, "");
    return (
      utility === "sr-only" ||
      utility === "hidden" ||
      utility === "invisible" ||
      utility === "opacity-0" ||
      /^opacity-\[0(?:\.0+)?\]$/.test(utility)
    );
  });
}

function expectReasonVisuallyDiscoverable(reason: HTMLElement | null) {
  expect(reason).not.toBeNull();
  expect(hiddenReasonUtility(reason?.className ?? "")).toBeUndefined();
  expect(reason?.hidden).toBe(false);
  expect(reason?.getAttribute("aria-hidden")).not.toBe("true");
  expect(reason?.style.display).not.toBe("none");
  expect(reason?.style.visibility).not.toBe("hidden");
  expect(reason?.style.opacity).not.toBe("0");
}

describe("EmailDetail unavailable reply actions", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    root = null;
    container?.remove();
    container = null;
    vi.unstubAllGlobals();
  });

  it.each([
    ["screen-reader-only utility", (reason: HTMLElement) => reason.classList.add("sr-only")],
    ["invisible utility", (reason: HTMLElement) => reason.classList.add("invisible")],
    ["responsive hidden utility", (reason: HTMLElement) => reason.classList.add("max-sm:hidden")],
    ["important hidden utility", (reason: HTMLElement) => reason.classList.add("md:!hidden")],
    ["zero-opacity utility", (reason: HTMLElement) => reason.classList.add("opacity-0")],
    ["inline display none", (reason: HTMLElement) => reason.style.setProperty("display", "none")],
    ["inline visibility hidden", (reason: HTMLElement) => reason.style.setProperty("visibility", "hidden")],
    ["inline zero opacity", (reason: HTMLElement) => reason.style.setProperty("opacity", "0")],
  ])("visibility guard rejects %s", (_label, hideReason) => {
    const reason = document.createElement("p");
    hideReason(reason);
    expect(() => expectReasonVisuallyDiscoverable(reason)).toThrow();
  });

  it("keeps unavailable reasons keyboard- and touch-discoverable and rejects whitespace draft commands", async () => {
    let draftRequests = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/emails/1")) {
        return jsonResponse({
          id: 1,
          message_id: "<reply@example.com>",
          thread_id: null,
          sender: "sender@example.com",
          recipients: "user@example.com",
          subject: "Reply boundary",
          date: "2026-09-09T00:00:00Z",
          body: "Please reply.",
        });
      }
      if (url.endsWith("/api/llm/summarize")) {
        return jsonResponse({ summary: "요약", action_items: [] });
      }
      if (url.endsWith("/api/llm/draft")) {
        draftRequests += 1;
        return jsonResponse({ draft: "should not be generated" });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<EmailDetail emailId={1} />);
    });
    await flushAsyncWork();

    const instruction = container.querySelector<HTMLInputElement>("#reply-instruction");
    expect(instruction).not.toBeNull();
    setInputValue(instruction!, "   ");
    await flushAsyncWork();

    const draftButton = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent?.includes("답장 초안 생성"),
    );
    expect(draftButton).toBeDefined();
    expect(draftButton?.disabled).toBe(true);

    const draftUnavailable = draftButton?.closest<HTMLElement>("[data-unavailable-action='reply-draft']");
    expect(draftUnavailable?.tabIndex).toBe(0);
    const draftReasonId = draftUnavailable?.getAttribute("aria-describedby");
    expect(draftReasonId).toBe("reply-draft-unavailable-reason");
    const draftReason = container.querySelector<HTMLElement>(`#${draftReasonId}`);
    expect(draftReason?.textContent).toBe("답장 초안 지시를 입력해주세요");
    expectReasonVisuallyDiscoverable(draftReason);

    const sendButton = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent?.includes("답장 보내기"),
    );
    expect(sendButton?.disabled).toBe(true);
    const sendUnavailable = sendButton?.closest<HTMLElement>("[data-unavailable-action='reply-send']");
    expect(sendUnavailable?.tabIndex).toBe(0);
    const sendReasonId = sendUnavailable?.getAttribute("aria-describedby");
    expect(sendReasonId).toBe("reply-send-unavailable-reason");
    const sendReason = container.querySelector<HTMLElement>(`#${sendReasonId}`);
    expect(sendReason?.textContent).toBe("답장 초안을 먼저 작성해주세요");
    expectReasonVisuallyDiscoverable(sendReason);

    await act(async () => {
      root?.render(
        <EmailDetail
          emailId={1}
          actionCommand={{ id: 9001, action: "reply-draft" }}
        />,
      );
    });
    await flushAsyncWork();

    expect(draftRequests).toBe(0);
  });
});
