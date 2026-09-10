/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import ToolsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a>,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/tools",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("lucide-react", () => ({
  Activity: () => <svg aria-hidden="true" />,
  AlertCircle: () => <svg aria-hidden="true" />,
  Loader2: () => <svg aria-hidden="true" data-testid="loader" />,
  Bell: () => <svg aria-hidden="true" />,
  Bot: () => <svg aria-hidden="true" />,
  CheckCircle2: () => <svg aria-hidden="true" />,
  Cpu: () => <svg aria-hidden="true" />,
  Mail: () => <svg aria-hidden="true" />,
  Monitor: () => <svg aria-hidden="true" />,
  Network: () => <svg aria-hidden="true" />,
  Plus: () => <svg aria-hidden="true" />,
  RefreshCw: () => <svg aria-hidden="true" />,
  Settings: () => <svg aria-hidden="true" />,
  Shield: () => <svg aria-hidden="true" />,
  Smartphone: () => <svg aria-hidden="true" />,
  User: () => <svg aria-hidden="true" />,
  Search: () => <svg aria-hidden="true" />,
  X: () => <svg aria-hidden="true" />,
  Inbox: () => <svg aria-hidden="true" />,
  Star: () => <svg aria-hidden="true" />,
  Send: () => <svg aria-hidden="true" />,
  CalendarDays: () => <svg aria-hidden="true" />,
  FolderDot: () => <svg aria-hidden="true" />,
  BarChart3: () => <svg aria-hidden="true" />,
  CheckSquare: () => <svg aria-hidden="true" />,
  FileText: () => <svg aria-hidden="true" />,
  HelpCircle: () => <svg aria-hidden="true" />,
  Home: () => <svg aria-hidden="true" />,
  MessageSquare: () => <svg aria-hidden="true" />,
  MoreHorizontal: () => <svg aria-hidden="true" />,
  Settings2: () => <svg aria-hidden="true" />,
  Users: () => <svg aria-hidden="true" />,
  Wallet: () => <svg aria-hidden="true" />,
  ArrowRight: () => <svg aria-hidden="true" />,
  Briefcase: () => <svg aria-hidden="true" />,
  Sparkles: () => <svg aria-hidden="true" />,
  Database: () => <svg aria-hidden="true" />,
  Lock: () => <svg aria-hidden="true" />,
  SlidersHorizontal: () => <svg aria-hidden="true" />,
  ChevronDown: () => <svg aria-hidden="true" />,
  Wrench: () => <svg aria-hidden="true" />,
  LogOut: () => <svg aria-hidden="true" />,
  ShieldCheck: () => <svg aria-hidden="true" />,
  PenLine: () => <svg aria-hidden="true" />,
  Menu: () => <svg aria-hidden="true" />,
  UserCircle: () => <svg aria-hidden="true" />,
  Play: () => <svg aria-hidden="true" />,
  Power: () => <svg aria-hidden="true" />,
}));

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    text: async () => JSON.stringify(body),
    json: async () => body,
  } as Response;
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("ToolsPage", () => {
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

  it("renders tools correctly with category", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        if (url.includes("/api/tools") && !url.includes("execute")) {
          return jsonResponse([
            { code: "test_tool", name: "테스트 도구", description: "설명입니다.", category: "테스트 카테고리" },
          ]);
        }
        return jsonResponse({});
      }),
    );

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<ToolsPage />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("테스트 도구");
    expect(container.textContent).toContain("설명입니다.");
    expect(container.textContent).toContain("테스트 카테고리");
  });

  it("executes a tool and shows the result", async () => {
    let executeCalled = false;
    let executeBody: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url, init) => {
        if (url.includes("/api/tools") && !url.includes("execute")) {
          return jsonResponse([
            {
              code: "test_tool",
              name: "테스트 도구",
              description: "설명",
              category: "카테고리",
              parameters: { thread_id: "string", limit: "integer" },
            },
          ]);
        }
        if (url.includes("/api/tools/test_tool/execute")) {
          executeCalled = true;
          executeBody = JSON.parse(String(init?.body));
          return jsonResponse({
            status: "success",
            result: "Execution OK",
            message: "Success message"
          });
        }
        return jsonResponse({});
      }),
    );

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<ToolsPage />);
    });
    await flushAsyncWork();

    const button = container.querySelector('button[data-tool-execute="test_tool"]');
    expect(button).not.toBeNull();
    const threadInput = container.querySelector(
      'textarea[data-tool-parameter="test_tool.thread_id"]',
    ) as HTMLTextAreaElement | null;
    const limitInput = container.querySelector(
      'input[data-tool-parameter="test_tool.limit"]',
    ) as HTMLInputElement | null;
    expect(threadInput).not.toBeNull();
    expect(limitInput).not.toBeNull();

    act(() => {
      if (!threadInput) throw new Error("Thread input was not rendered.");
      const setNativeValue = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        "value",
      )?.set;
      setNativeValue?.call(threadInput, "user-provided content");
      threadInput.dispatchEvent(new Event("input", { bubbles: true }));
      const setNativeNumberValue = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set;
      setNativeNumberValue?.call(limitInput, "2");
      limitInput?.dispatchEvent(new Event("input", { bubbles: true }));
    });

    act(() => {
      button?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await flushAsyncWork();

    expect(executeCalled).toBe(true);
    expect(executeBody).toEqual({ parameters: { thread_id: "user-provided content", limit: 2 } });
    expect(container.textContent).toContain("성공");
    expect(container.textContent).toContain("Execution OK");
    expect(container.textContent).not.toContain("Success message");
  });

  it("preserves structured drafts and rejects fractional integer input", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        if (url.includes("/api/tools") && !url.includes("execute")) {
          return jsonResponse([
            {
              code: "structured_tool",
              name: "구조화 도구",
              description: "설명",
              category: "카테고리",
              parameters: { payload: "object", count: "integer" },
            },
          ]);
        }
        return jsonResponse({ status: "success", result: "ok" });
      }),
    );

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root?.render(<ToolsPage />));
    await flushAsyncWork();

    const payload = container.querySelector(
      'input[data-tool-parameter="structured_tool.payload"]',
    ) as HTMLInputElement;
    const count = container.querySelector(
      'input[data-tool-parameter="structured_tool.count"]',
    ) as HTMLInputElement;
    const execute = container.querySelector(
      'button[data-tool-execute="structured_tool"]',
    ) as HTMLButtonElement;

    act(() => {
      const inputSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      inputSetter?.call(payload, "{");
      payload.dispatchEvent(new Event("input", { bubbles: true }));
      inputSetter?.call(count, "1.5");
      count.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(payload.value).toBe("{");
    expect(payload.getAttribute("aria-invalid")).toBe("true");
    expect(count.getAttribute("aria-invalid")).toBe("true");
    expect(execute.disabled).toBe(true);
  });

  it("rebuilds parameter values when the tool schema is refreshed", async () => {
    let catalogRequestCount = 0;
    let executeBody: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url, init) => {
        if (url.includes("/api/tools") && !url.includes("execute")) {
          catalogRequestCount += 1;
          return jsonResponse([
            {
              code: "test_tool",
              name: "테스트 도구",
              description: "설명",
              category: "카테고리",
              parameters:
                catalogRequestCount === 1
                  ? { removed: "string", changed: "string" }
                  : { changed: { type: "number" }, fresh: "string" },
            },
          ]);
        }
        if (url.includes("/api/tools/test_tool/execute")) {
          executeBody = JSON.parse(String(init?.body));
          return jsonResponse({ status: "success", result: "Execution OK" });
        }
        return jsonResponse({});
      }),
    );

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<ToolsPage />);
    });
    await flushAsyncWork();

    const refreshButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("새로고침"),
    );
    expect(refreshButton).not.toBeUndefined();
    act(() => {
      refreshButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();

    const executeButton = container.querySelector('button[data-tool-execute="test_tool"]');
    act(() => {
      executeButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();

    expect(executeBody).toEqual({ parameters: { changed: 0, fresh: "" } });
  });

  it("shows error when tool execution fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        if (url.includes("/api/tools") && !url.includes("execute")) {
          return jsonResponse([
            { code: "test_tool", name: "테스트 도구", description: "설명", category: "카테고리" },
          ]);
        }
        if (url.includes("/api/tools/test_tool/execute")) {
          return jsonResponse(null, false, 500);
        }
        return jsonResponse({});
      }),
    );

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<ToolsPage />);
    });
    await flushAsyncWork();

    const button = container.querySelector('button[data-tool-execute="test_tool"]');

    act(() => {
      button?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("실패");
    expect(container.textContent).toContain("API request failed");
  });

  it("submits optional schemas and shows bounded stable failures", async () => {
    let executeBody: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url, init) => {
        if (url.includes("/api/tools") && !url.includes("execute")) {
          return jsonResponse([
            {
              code: "bounded_tool",
              name: "제한 도구",
              description: "설명",
              category: "카테고리",
              parameters: {
                required_text: { type: "string", max_length: 12 },
                optional_text: { type: "string", required: false },
              },
            },
          ]);
        }
        if (url.includes("/api/tools/bounded_tool/execute")) {
          executeBody = JSON.parse(String(init?.body));
          return jsonResponse({
            status: "failed",
            result: null,
            message: "입력값을 확인하세요.",
            error_code: "tool_parameter_too_long",
          });
        }
        return jsonResponse({});
      }),
    );

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root?.render(<ToolsPage />));
    await flushAsyncWork();

    const requiredInput = container.querySelector(
      'textarea[data-tool-parameter="bounded_tool.required_text"]',
    ) as HTMLTextAreaElement;
    const executeButton = container.querySelector(
      'button[data-tool-execute="bounded_tool"]',
    );
    expect(requiredInput.maxLength).toBe(12);
    expect(requiredInput.getAttribute("aria-describedby")).toBe(
      "tool-bounded_tool-required_text-help",
    );
    expect(container.textContent).toContain("최대 12자");

    act(() => executeButton?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await flushAsyncWork();

    expect(executeBody).toEqual({ parameters: { required_text: "" } });
    expect(container.textContent).toContain("입력값을 확인하세요.");
    expect(container.textContent).toContain("입력 길이를 줄인 뒤 다시 실행하세요.");
    expect(container.textContent).not.toContain("tool_parameter_too_long");
  });

  it("distinguishes a load failure from an empty tool list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(null, false, 500)),
    );

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(<ToolsPage />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("도구 목록을 불러오지 못했습니다.");
    expect(container.textContent).not.toContain("사용 가능한 도구가 없습니다.");
  });
});
