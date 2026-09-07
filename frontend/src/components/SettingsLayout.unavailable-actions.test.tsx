/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("lucide-react", () => ({
  Activity: () => <svg aria-hidden="true" />,
  AlertCircle: () => <svg aria-hidden="true" />,
  Loader2: () => <svg aria-hidden="true" />,
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
}));

const oidcMocks = vi.hoisted(() => ({
  clearOidcSession: vi.fn(),
  getOidcBrowserConfig: vi.fn(),
  startOidcLogin: vi.fn(),
}));

vi.mock("@/lib/oidc-session", () => ({
  clearOidcSession: oidcMocks.clearOidcSession,
  getOidcBrowserConfig: oidcMocks.getOidcBrowserConfig,
  startOidcLogin: oidcMocks.startOidcLogin,
}));

import { SettingsLayout } from "./SettingsLayout";

const accountConfig = {
  user_id: "default",
  smtp_server: "smtp.example.com",
  smtp_port: 587,
  smtp_username: "sender@example.com",
  has_smtp_password: true,
  imap_server: "imap.example.com",
  imap_port: 993,
  imap_username: "inbox@example.com",
  has_imap_password: true,
  pop3_server: "pop3.example.com",
  pop3_port: 995,
  pop3_username: "archive@example.com",
  has_pop3_password: false,
  oauth_client_id: "oauth-client-id",
  oauth_redirect_uri: "https://naruon.net/oauth/mail/callback",
  has_oauth_client_secret: true,
};

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

function installFetch(options?: {
  accountPut?: Promise<Response>;
  runnerRotate?: Promise<Response>;
  userId?: string | null;
}) {
  const userId = options?.userId === undefined ? "alice" : options.userId;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/auth/session") {
      return jsonResponse({
        authenticated: userId !== null,
        claims: {
          userId,
          organizationId: userId ? "org-acme" : null,
          workspaceId: userId ? "workspace-org-acme" : null,
        },
      });
    }
    if (url === "/api/accounts/config" && init?.method === "PUT") {
      return options?.accountPut ?? jsonResponse(accountConfig);
    }
    if (url === "/api/accounts/config") return jsonResponse(accountConfig);
    if (url === "/api/calendar/writeback-sources") return jsonResponse([]);
    if (url === "/api/webdav/accounts") return jsonResponse([]);
    if (url === "/api/llm-providers") return jsonResponse([]);
    if (url === "/api/runner-config/rotate" && init?.method === "POST") {
      return options?.runnerRotate ?? jsonResponse({
        workspace_id: "workspace-org-acme",
        configured: true,
        fingerprint: "***rotated",
        updated_at: "2026-09-08T00:00:00Z",
        connector_manifest: {
          role: "self-hosted_connector",
          network_mode: "outbound_only",
          control_plane_domain: "naruon.net",
          local_protocols: ["imap", "smtp"],
          prohibited_roles: ["smtp_server", "imap_server", "mx_host"],
          runner_usage: "ci_smoke_only",
        },
      });
    }
    if (url === "/api/runner-config") {
      return jsonResponse({
        workspace_id: "workspace-org-acme",
        configured: true,
        fingerprint: "***configured",
        updated_at: "2026-09-08T00:00:00Z",
        connector_manifest: {
          role: "self-hosted_connector",
          network_mode: "outbound_only",
          control_plane_domain: "naruon.net",
          local_protocols: ["imap", "smtp"],
          prohibited_roles: ["smtp_server", "imap_server", "mx_host"],
          runner_usage: "ci_smoke_only",
        },
      });
    }
    if (url === "/api/observability/operational-signals") {
      return jsonResponse({
        workspace_id: "workspace-org-acme",
        audit_event: "observability.operational_signals.viewed",
        telemetry: {
          prometheus_metrics_enabled: true,
          otel_traces_enabled: true,
          otel_endpoint_configured: false,
          otel_endpoint_host: null,
        },
        connector: {
          workspace_id: "workspace-org-acme",
          registration_state: "registration_configured",
          connection_state: "connected",
          active_connection_count: 1,
          control_plane_domain: "naruon.net",
          network_mode: "outbound_only",
          runner_usage: "ci_smoke_only",
          local_protocols: ["imap", "smtp"],
          last_heartbeat_at: "2026-09-08T00:00:00Z",
          last_disconnect_at: null,
          queue_depth_state: "clear",
          queue_depth: {
            pending_count: 0,
            running_count: 0,
            failed_count: 0,
            total_count: 0,
            next_retry_at: null,
          },
          recent_events: [],
        },
        signals: [],
      });
    }
    return jsonResponse({});
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function settle() {
  await Promise.resolve();
  await Promise.resolve();
}

function buttonByText(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent === text,
  );
}

describe("SettingsLayout unavailable actions", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  beforeEach(() => {
    oidcMocks.getOidcBrowserConfig.mockReturnValue({
      issuerUrl: "https://login.example.com/realms/naruon",
      clientId: "naruon-web",
      redirectUri: "https://app.example.com/auth/callback",
      scope: "openid profile email",
      authorizationEndpoint: "https://login.example.com/realms/naruon/protocol/openid-connect/auth",
      tokenEndpoint: "https://login.example.com/realms/naruon/protocol/openid-connect/token",
      endSessionEndpoint: "https://login.example.com/realms/naruon/protocol/openid-connect/logout",
    });
  });

  afterEach(() => {
    if (root) act(() => root?.unmount());
    root = null;
    container?.remove();
    container = null;
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("keeps account save and token rotation focusable but blocks repeated activation while pending", async () => {
    const accountPut = deferredResponse();
    const runnerRotate = deferredResponse();
    const fetchMock = installFetch({
      accountPut: accountPut.promise,
      runnerRotate: runnerRotate.promise,
    });

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SettingsLayout />);
      await settle();
    });

    await act(async () => {
      buttonByText(container!, "연결 계정")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await settle();
    });

    const saveButton = buttonByText(container, "계정 설정 저장");
    const saveForm = saveButton?.closest("form");
    expect(saveButton).toBeTruthy();
    expect(saveForm).toBeTruthy();
    expect(saveButton?.getAttribute("aria-describedby")).toBe("account-save-tooltip");

    await act(async () => {
      saveForm?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await settle();
    });

    expect(buttonByText(container, "저장 중")?.getAttribute("aria-disabled")).toBe("true");
    expect(container.querySelector("#account-save-tooltip")?.textContent).toContain("저장 중입니다");
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input) === "/api/accounts/config" && init?.method === "PUT")).toHaveLength(1);

    await act(async () => {
      saveForm?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await settle();
    });
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input) === "/api/accounts/config" && init?.method === "PUT")).toHaveLength(1);

    accountPut.resolve(jsonResponse(accountConfig));
    await act(async () => {
      await settle();
    });

    await act(async () => {
      buttonByText(container!, "개발자")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await settle();
    });

    const rotateButton = buttonByText(container, "등록 토큰 회전");
    expect(rotateButton?.getAttribute("aria-describedby")).toBe("runner-rotate-tooltip");
    await act(async () => {
      rotateButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await settle();
    });

    const rotatingButton = buttonByText(container, "회전 중");
    expect(rotatingButton?.getAttribute("aria-disabled")).toBe("true");
    expect(container.querySelector("#runner-rotate-tooltip")?.textContent).toContain("회전 중입니다");
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input) === "/api/runner-config/rotate" && init?.method === "POST")).toHaveLength(1);

    await act(async () => {
      rotatingButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await settle();
    });
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input) === "/api/runner-config/rotate" && init?.method === "POST")).toHaveLength(1);

    runnerRotate.resolve(jsonResponse({
      workspace_id: "workspace-org-acme",
      configured: true,
      fingerprint: "***rotated",
      updated_at: "2026-09-08T00:00:00Z",
      connector_manifest: {
        role: "self-hosted_connector",
        network_mode: "outbound_only",
        control_plane_domain: "naruon.net",
        local_protocols: ["imap", "smtp"],
        prohibited_roles: ["smtp_server", "imap_server", "mx_host"],
        runner_usage: "ci_smoke_only",
      },
    }));
    await act(async () => {
      await settle();
    });
  });

  it("keeps unavailable OIDC actions discoverable without executing them", async () => {
    oidcMocks.getOidcBrowserConfig.mockReturnValue(null);
    installFetch({ userId: null });

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SettingsLayout />);
      await settle();
    });
    await act(async () => {
      buttonByText(container!, "개발자")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await settle();
    });

    const loginButton = buttonByText(container, "OIDC 로그인");
    const logoutButton = buttonByText(container, "로그아웃");
    expect(loginButton?.getAttribute("aria-disabled")).toBe("true");
    expect(loginButton?.getAttribute("aria-describedby")).toBe("oidc-login-tooltip");
    expect(container.querySelector("#oidc-login-tooltip")?.textContent).toContain("OIDC 브라우저 설정이 없습니다");
    expect(logoutButton?.getAttribute("aria-disabled")).toBe("true");
    expect(logoutButton?.getAttribute("aria-describedby")).toBe("oidc-logout-tooltip");
    expect(container.querySelector("#oidc-logout-tooltip")?.textContent).toContain("로그인된 세션이 없습니다");

    await act(async () => {
      loginButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      logoutButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await settle();
    });

    expect(oidcMocks.startOidcLogin).not.toHaveBeenCalled();
    expect(oidcMocks.clearOidcSession).not.toHaveBeenCalled();
  });
});
