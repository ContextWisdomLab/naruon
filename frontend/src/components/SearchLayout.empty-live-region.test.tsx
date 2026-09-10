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

function statusWithText(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll<HTMLElement>('[role="status"]')).find(
    (element) => element.textContent?.includes(text),
  ) ?? null;
}

describe("SearchLayout empty-result live region", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    root = null;
    container?.remove();
    container = null;
    vi.unstubAllGlobals();
  });

  it("announces an empty result after the asynchronous search leaves loading", async () => {
    let resolveSearch!: (response: Response) => void;
    const searchResponse = new Promise<Response>((resolve) => {
      resolveSearch = resolve;
    });
    const emptyBody = Promise.resolve({ results: [] });

    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/search/answer")) {
        return Promise.resolve(jsonResponse({ answer: null, citations: [], provenance: null }));
      }
      if (url.endsWith("/api/search")) return searchResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SearchLayout />);
    });

    expect(statusWithText(container, "맥락 검색 결과를 불러오는 중입니다.")).not.toBeNull();
    expect(statusWithText(container, "맥락 검색 결과가 없습니다.")).toBeNull();

    await act(async () => {
      resolveSearch(new Response(JSON.stringify(await emptyBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
      await searchResponse;
      await emptyBody;
    });

    const emptyStatus = statusWithText(container, "맥락 검색 결과가 없습니다.");
    expect(emptyStatus).not.toBeNull();
    expect(emptyStatus?.getAttribute("aria-live")).toBe("polite");
    expect(container.textContent).not.toContain("맥락 검색 결과를 불러오는 중입니다.");
  });
});