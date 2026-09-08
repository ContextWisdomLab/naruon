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

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("SettingsLayout", () => {
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input) === "/auth/session") {
          return jsonResponse({
            authenticated: true,
            claims: {
              userId: "alice",
              organizationId: "org-acme",
              workspaceId: "workspace-org-acme",
            },
          });
        }
        if (String(input) === "/api/runner-config") {
          return jsonResponse({
            workspace_id: "workspace-org-acme",
            configured: true,
            fingerprint: "***abc12345",
            updated_at: "2026-05-27T06:00:00Z",
            connector_manifest: {
              role: "self-hosted_connector",
              network_mode: "outbound_only",
              control_plane_domain: "naruon.net",
              local_protocols: ["imap", "pop3", "smtp", "caldav", "carddav", "webdav"],
              prohibited_roles: ["smtp_server", "imap_server", "mx_host"],
              runner_usage: "ci_smoke_only",
            },
          });
        }
        if (String(input) === "/api/runner-config/rotate" && init?.method === "POST") {
          return jsonResponse({
            workspace_id: "workspace-org-acme",
            configured: true,
            fingerprint: "***rotated",
            updated_at: "2026-05-27T07:00:00Z",
            connector_manifest: {
              role: "self-hosted_connector",
              network_mode: "outbound_only",
              control_plane_domain: "naruon.net",
              local_protocols: ["imap", "pop3", "smtp", "caldav", "carddav", "webdav"],
              prohibited_roles: ["smtp_server", "imap_server", "mx_host"],
              runner_usage: "ci_smoke_only",
            },
          });
        }
        if (String(input) === "/api/observability/operational-signals") {
          return jsonResponse({
            workspace_id: "workspace-org-acme",
            audit_event: "observability.operational_signals.viewed",
            telemetry: {
              prometheus_metrics_enabled: true,
              otel_traces_enabled: true,
              otel_endpoint_configured: true,
              otel_endpoint_host: "otel-collector:4317",
            },
            connector: {
              workspace_id: "workspace-org-acme",
              registration_state: "registration_configured",
              connection_state: "connected",
              active_connection_count: 1,
              control_plane_domain: "naruon.net",
              network_mode: "outbound_only",
              runner_usage: "ci_smoke_only",
              local_protocols: ["imap", "pop3", "smtp", "caldav", "carddav", "webdav"],
              last_heartbeat_at: "2026-05-27T12:00:00Z",
              last_disconnect_at: null,
              queue_depth_state: "degraded",
              queue_depth: {
                pending_count: 2,
                running_count: 1,
                failed_count: 1,
                total_count: 4,
                next_retry_at: "2026-06-15T12:05:00Z",
              },
              recent_events: [
                {
                  event_uid: "connector_evt_heartbeat",
                  signal_key: "connector_heartbeat",
                  state_code: "heartbeat",
                  detail_text: "outbound runner heartbeat received",
                  observed_at: "2026-05-27T12:00:00Z",
                },
                {
                  event_uid: "connector_evt_connected",
                  signal_key: "connector_heartbeat",
                  state_code: "connected",
                  detail_text: "outbound runner socket connected",
                  observed_at: "2026-05-27T11:59:00Z",
                },
              ],
            },
            signals: [
              {
                signal_key: "connector_heartbeat",
                display_name: "Connector heartbeat",
                state: "enabled",
                evidence_source: "runner WebSocket manager",
                detail: "Live heartbeat uses active outbound runner sockets.",
                provider_write_executed: false,
              },
              {
                signal_key: "writeback_retry_queue",
                display_name: "Writeback retry queue",
                state: "enabled",
                evidence_source: "provider_writeback_retry_items",
                detail: "4 queued writeback retry items are tracked by state.",
                provider_write_executed: false,
              },
              {
                signal_key: "sync_lag",
                display_name: "Sync lag",
                state: "instrumentation_pending",
                evidence_source: "provider adapters",
                detail: "Provider sync lag will be emitted by source-backed connector jobs.",
                provider_write_executed: false,
              },
            ],
          });
        }
        if (String(input) === "/api/calendar/writeback-sources") {
          return jsonResponse([
            {
              source_id: "caldav_src_fastmail_primary",
              provider: "Fastmail",
              protocol: "caldav",
              owner_id: "default",
              organization_id: "org-acme",
              capabilities: ["read", "write", "etag"],
              writeback_enabled: true,
              etag: "etag-caldav-primary",
            },
          ]);
        }
        if (String(input) === "/api/webdav/accounts") {
          return jsonResponse([
            {
              source_id: "webdav_src_primary",
              display_label: "WebDAV source webdav_src_primary",
              writeback_enabled: true,
            },
          ]);
        }
        if (String(input) === "/api/llm-providers" && init?.method === "POST") {
          const body = JSON.parse(String(init.body));
          return jsonResponse({
            id: 2,
            name: body.name,
            provider_type: body.provider_type,
            base_url: body.base_url,
            model_identifier: body.model_identifier,
            embedding_model: body.embedding_model,
            is_active: body.is_active,
            configured: true,
            fingerprint: body.api_key ? "***1234" : null,
            updated_at: "2026-06-11T04:00:00Z",
          });
        }
        if ((String(input) === "/api/llm-providers/1" || String(input) === "/api/llm-providers/2") && init?.method === "PUT") {
          const body = JSON.parse(String(init.body));
          return jsonResponse({
            id: String(input).endsWith("/2") ? 2 : 1,
            name: String(input).endsWith("/2") ? "Local Gemma4" : "Primary OpenAI",
            provider_type: String(input).endsWith("/2") ? "ollama" : "openai",
            base_url: String(input).endsWith("/2") ? "http://ollama:11434/v1" : "https://api.openai.com/v1",
            model_identifier: body.model_identifier,
            embedding_model: body.embedding_model,
            is_active: true,
            configured: true,
            fingerprint: String(input).endsWith("/2") ? null : "***1234",
            updated_at: "2026-06-11T05:00:00Z",
          });
        }
        if (String(input) === "/api/llm-providers") {
          return jsonResponse([
            {
              id: 1,
              name: "Primary OpenAI",
              provider_type: "openai",
              base_url: "https://api.openai.com/v1",
              model_identifier: "gpt-5.4",
              embedding_model: "text-embedding-3-small",
              is_active: true,
              configured: true,
              fingerprint: "***1234",
              updated_at: "2026-06-11T03:00:00Z",
            },
          ]);
        }
        if (String(input) === "/api/accounts/config" && init?.method === "PUT") {
          const body = JSON.parse(String(init.body));
          return jsonResponse({
            user_id: "default",
            smtp_server: body.smtp_server,
            smtp_port: body.smtp_port,
            smtp_username: body.smtp_username,
            has_smtp_password: false,
            imap_server: body.imap_server,
            imap_port: body.imap_port,
            imap_username: body.imap_username,
            has_imap_password: true,
            pop3_server: body.pop3_server,
            pop3_port: body.pop3_port,
            pop3_username: body.pop3_username,
            has_pop3_password: false,
            oauth_client_id: body.oauth_client_id,
            oauth_redirect_uri: body.oauth_redirect_uri,
            has_oauth_client_secret: true,
          });
        }
        if (String(input) === "/api/accounts/config") {
          return jsonResponse({
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
          });
        }
        return jsonResponse({});
      }),
    );
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

  it("renders the self-hosted connector manifest and keeps mobile settings tabs reachable", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SettingsLayout />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const mobileSettingsNav = container.querySelector('nav[aria-label="설정 섹션"]');
    expect(mobileSettingsNav?.textContent).toContain("개발자");

    const developerButtons = Array.from(container.querySelectorAll("button")).filter((button) => button.textContent?.includes("개발자"));
    await act(async () => {
      developerButtons[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/runner-config",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/observability/operational-signals",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.any(Object),
      }),
    );
    const operationalCall = vi.mocked(fetch).mock.calls.find(([input]) => String(input) === "/api/observability/operational-signals");
    expect(operationalCall?.[1]?.headers).not.toHaveProperty("X-User-Id");
    expect(operationalCall?.[1]?.headers).not.toHaveProperty("X-Organization-Id");
    expect(operationalCall?.[1]?.headers).not.toHaveProperty("X-Group-Id");
    expect(operationalCall?.[1]?.headers).not.toHaveProperty("X-Group-Ids");
    expect(operationalCall?.[1]?.headers).not.toHaveProperty("X-User-Role");
    expect(operationalCall?.[1]?.headers).not.toHaveProperty("X-Dev-Auth-Token");
    expect(container.textContent).toContain("Self-hosted connector 등록 상태");
    expect(container.textContent).toContain("Naruon은 메일 서버가 아닙니다");
    expect(container.textContent).toContain("Self-hosted connector");
    expect(container.textContent).toContain("Outbound only");
    expect(container.textContent).toContain("제어 평면");
    expect(container.textContent).toContain("검증용 연결");
    expect(container.textContent).toContain("CALDAV");
    expect(container.textContent).toContain("WEBDAV");
    expect(container.textContent).toContain("SMTP 서버 역할 금지");
    expect(container.textContent).toContain("IMAP 서버 역할 금지");
    expect(container.textContent).toContain("MX 호스트 역할 금지");
    expect(container.textContent).toContain("Connector 상태와 APM 신호");
    expect(container.textContent).toContain("감사 근거 기록됨");
    expect(container.textContent).toContain("연결됨");
    expect(container.textContent).toContain("OTel endpoint");
    expect(container.textContent).toContain("최근 connector 신호");
    expect(container.textContent).toContain("Writeback retry queue");
    expect(container.textContent).toContain("재시도 대기 2건");
    expect(container.textContent).toContain("실패 1건");
    expect(container.textContent).toContain("하트비트 수신");
    expect(container.textContent).toContain("서버가 runner 하트비트를 관측했습니다");
    expect(container.textContent).not.toContain("self-hosted_connector");
    expect(container.textContent).not.toContain("outbound_only");
    expect(container.textContent).not.toContain("ci_smoke_only");
    expect(container.textContent).not.toContain("smtp_server");
    expect(container.textContent).not.toContain("imap_server");
    expect(container.textContent).not.toContain("mx_host");
    expect(container.textContent).not.toContain("observability.operational_signals.viewed");
    expect(container.textContent).not.toContain("connector_evt_heartbeat");
    expect(container.textContent).not.toContain("outbound runner heartbeat received");
    expect(container.textContent).not.toContain("Provider sync lag will be emitted");
    expect(container.textContent).not.toContain("otel-collector:4317");
    expect(container.textContent).not.toContain("nrn_registered-token");
    expect(container.textContent).toContain("Connector heartbeat");
    expect(container.textContent).toContain("계측 준비");

    const rotateButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("등록 토큰 회전"));
    expect(rotateButton).toBeTruthy();
    await act(async () => {
      rotateButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    const rotateCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input) === "/api/runner-config/rotate" && init?.method === "POST");
    expect(rotateCall?.[1]?.credentials).toBe("same-origin");
    expect(rotateCall?.[1]?.headers).not.toHaveProperty("Authorization");
    expect(rotateCall?.[1]?.headers).not.toHaveProperty("X-User-Id");
    expect(rotateCall?.[1]?.headers).not.toHaveProperty("X-Organization-Id");
    expect(rotateCall?.[1]?.headers).not.toHaveProperty("X-Dev-Auth-Token");
    expect(container.textContent).toContain("등록 토큰이 생성되었습니다");
    expect(container.textContent).toContain("원문 토큰은 화면에 보관하지 않습니다");
    expect(container.textContent).not.toMatch(/nrn_[A-Za-z0-9_-]+/);
    expect(container.textContent).toContain("***rotated");
  });

  it("marks external operational console links with explicit noopener", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SettingsLayout />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const developerTab = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "개발자",
    );
    expect(developerTab).toBeTruthy();
    await act(async () => {
      developerTab?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    const externalLinks = Array.from(
      container.querySelectorAll<HTMLAnchorElement>('a[target="_blank"]'),
    );
    expect(externalLinks.map((link) => link.textContent)).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Grafana"),
        expect.stringContaining("Keycloak"),
        expect.stringContaining("Loki"),
        expect.stringContaining("Tempo"),
      ]),
    );
    for (const link of externalLinks) {
      expect(link.rel.split(/\s+/).sort()).toEqual(["noopener", "noreferrer"]);
    }
  });

  it("wires Keycloak OIDC login and logout controls to the stored bearer session", async () => {
    window.history.pushState({}, "", "/settings");
    oidcMocks.clearOidcSession.mockResolvedValue(undefined);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SettingsLayout />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const developerTab = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "개발자",
    );
    expect(developerTab).toBeTruthy();
    await act(async () => {
      developerTab?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("OIDC 인증 세션");
    expect(container.textContent).toContain("Issuer");
    expect(container.textContent).toContain("Client");
    expect(container.textContent).toContain("설정됨");
    expect(container.textContent).toContain("등록됨");
    expect(container.textContent).toContain("서명된 세션 연결됨 · 조직 스코프");
    expect(container.textContent).not.toContain("https://login.example.com/realms/naruon");
    expect(container.textContent).not.toContain("naruon-web");
    expect(container.textContent).not.toContain("alice / org-acme / workspace-org-acme");

    const loginButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "OIDC 로그인");
    const logoutButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "로그아웃");
    expect(loginButton).toBeTruthy();
    expect(logoutButton).toBeTruthy();

    await act(async () => {
      loginButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
    });
    expect(oidcMocks.startOidcLogin).toHaveBeenCalledWith({ returnTo: "/settings" });

    await act(async () => {
      logoutButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(oidcMocks.clearOidcSession).toHaveBeenCalledWith({
      postLogoutRedirectUri: "http://localhost:3000",
    });
  });

  it("loads and saves source-backed mail account settings without public identity headers or secret replay", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SettingsLayout />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const accountButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "연결 계정");
    expect(accountButton).toBeTruthy();
    await act(async () => {
      accountButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/accounts/config",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
    const configGetCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input) === "/api/accounts/config" && init?.method !== "PUT");
    expect(configGetCall?.[1]?.headers).not.toHaveProperty("X-User-Id");
    expect(configGetCall?.[1]?.headers).not.toHaveProperty("X-Organization-Id");
    expect(configGetCall?.[1]?.headers).not.toHaveProperty("X-Group-Id");
    expect(configGetCall?.[1]?.headers).not.toHaveProperty("X-Group-Ids");
    expect(configGetCall?.[1]?.headers).not.toHaveProperty("X-User-Role");
    expect(configGetCall?.[1]?.headers).not.toHaveProperty("X-Dev-Auth-Token");
    const calendarSourcesCall = vi.mocked(fetch).mock.calls.find(([input]) => String(input) === "/api/calendar/writeback-sources");
    const webdavAccountsCall = vi.mocked(fetch).mock.calls.find(([input]) => String(input) === "/api/webdav/accounts");
    expect(calendarSourcesCall?.[1]?.credentials).toBe("same-origin");
    expect(webdavAccountsCall?.[1]?.credentials).toBe("same-origin");
    expect(calendarSourcesCall?.[1]?.headers).not.toHaveProperty("Authorization");
    expect(webdavAccountsCall?.[1]?.headers).not.toHaveProperty("Authorization");
    for (const sourceCall of [calendarSourcesCall, webdavAccountsCall]) {
      expect(sourceCall?.[1]?.headers).not.toHaveProperty("X-User-Id");
      expect(sourceCall?.[1]?.headers).not.toHaveProperty("X-Organization-Id");
      expect(sourceCall?.[1]?.headers).not.toHaveProperty("X-Group-Id");
      expect(sourceCall?.[1]?.headers).not.toHaveProperty("X-Group-Ids");
      expect(sourceCall?.[1]?.headers).not.toHaveProperty("X-User-Role");
      expect(sourceCall?.[1]?.headers).not.toHaveProperty("X-Dev-Auth-Token");
    }

    expect(container.textContent).toContain("고객 지정 연결");
    expect(container.textContent).toContain("smtp.example.com:587");
    expect(container.textContent).toContain("imap.example.com:993");
    expect(container.textContent).toContain("pop3.example.com:995");
    expect(container.textContent).toContain("OAuth 로그인");
    expect(container.textContent).toContain("앱 설정 완료, 사용자 consent 대기");
    expect(container.textContent).toContain("원본 연결 준비 상태");
    expect(container.textContent).toContain("Fastmail 일정 원본 1");
    expect(container.textContent).toContain("WebDAV 저장소 1");
    expect(container.textContent).not.toContain("caldav_src_fastmail_primary");
    expect(container.textContent).not.toContain("webdav_src_primary");
    expect(container.textContent).not.toContain("WebDAV source webdav_src_primary");
    expect(container.textContent).not.toContain("https://files.example.com/dav");
    expect(container.textContent).not.toContain("files@example.com");
    expect(container.textContent).toContain("쓰기 의도 가능");
    expect(container.textContent).toContain("충돌 검사용 ETag 준비");
    expect(container.textContent).not.toContain("etag-caldav-primary");
    expect(container.textContent).toContain("저장된 secret 유지");
    expect(container.textContent).toContain("Naruon은 메일함 용량이나 SMTP/IMAP 서버를 제공하지 않습니다");

    const saveButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "계정 설정 저장");
    expect(saveButton).toBeTruthy();
    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    const putCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input) === "/api/accounts/config" && init?.method === "PUT");
    expect(putCall).toBeTruthy();
    expect(putCall?.[1]?.headers).not.toHaveProperty("X-User-Id");
    expect(putCall?.[1]?.headers).not.toHaveProperty("X-Organization-Id");
    expect(putCall?.[1]?.headers).not.toHaveProperty("X-Group-Id");
    expect(putCall?.[1]?.headers).not.toHaveProperty("X-Group-Ids");
    expect(putCall?.[1]?.headers).not.toHaveProperty("X-User-Role");
    expect(putCall?.[1]?.headers).not.toHaveProperty("X-Dev-Auth-Token");
    const putBody = JSON.parse(String(putCall?.[1]?.body));
    expect(putBody).toMatchObject({
      smtp_server: "smtp.example.com",
      smtp_port: 587,
      smtp_username: "sender@example.com",
      imap_server: "imap.example.com",
      imap_port: 993,
      imap_username: "inbox@example.com",
      pop3_server: "pop3.example.com",
      pop3_port: 995,
      pop3_username: "archive@example.com",
      oauth_client_id: "oauth-client-id",
      oauth_redirect_uri: "https://naruon.net/oauth/mail/callback",
    });
    expect(putBody).not.toHaveProperty("smtp_password");
    expect(putBody).not.toHaveProperty("imap_password");
    expect(putBody).not.toHaveProperty("pop3_password");
    expect(putBody).not.toHaveProperty("oauth_client_secret");
    expect(container.textContent).toContain("계정 설정을 저장했습니다");
  });

  it("loads and saves AI model registry entries without public identity headers or secret replay", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SettingsLayout />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const modelButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "AI 모델");
    expect(modelButton).toBeTruthy();
    await act(async () => {
      modelButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    const providerListCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input) === "/api/llm-providers" && init?.method !== "POST");
    expect(providerListCall?.[1]?.credentials).toBe("same-origin");
    expect(providerListCall?.[1]?.headers).not.toHaveProperty("Authorization");
    expect(providerListCall?.[1]?.headers).not.toHaveProperty("X-User-Id");
    expect(providerListCall?.[1]?.headers).not.toHaveProperty("X-Organization-Id");
    expect(providerListCall?.[1]?.headers).not.toHaveProperty("X-Group-Id");
    expect(providerListCall?.[1]?.headers).not.toHaveProperty("X-Group-Ids");
    expect(providerListCall?.[1]?.headers).not.toHaveProperty("X-User-Role");
    expect(providerListCall?.[1]?.headers).not.toHaveProperty("X-Dev-Auth-Token");
    expect(container.textContent).toContain("등록된 모델 레지스트리");
    expect(container.textContent).toContain("Primary OpenAI");
    expect(container.textContent).toContain("gpt-5.4");
    expect(container.textContent).toContain("text-embedding-3-small");
    expect(container.textContent).toContain("Gemma4 로컬 모델 등록");
    expect(container.textContent).toContain("제공자 유형");
    expect(container.textContent).toContain("연결 엔드포인트");
    expect(container.textContent).toContain("API 엔드포인트");
    expect(container.textContent).toContain("로컬 API 키 대체값");
    expect(container.textContent).not.toContain("Provider");
    expect(container.textContent).not.toContain("Endpoint");
    expect(container.textContent).not.toContain("Local API key override");
    expect(container.textContent).not.toContain("sk-");

    const localRegisterButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("Gemma4 로컬 모델 등록"));
    expect(localRegisterButton).toBeTruthy();
    await act(async () => {
      localRegisterButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    const providerPostCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input) === "/api/llm-providers" && init?.method === "POST");
    expect(providerPostCall?.[1]?.credentials).toBe("same-origin");
    expect(providerPostCall?.[1]?.headers).not.toHaveProperty("Authorization");
    expect(providerPostCall?.[1]?.headers).not.toHaveProperty("X-User-Id");
    expect(providerPostCall?.[1]?.headers).not.toHaveProperty("X-Organization-Id");
    expect(providerPostCall?.[1]?.headers).not.toHaveProperty("X-Dev-Auth-Token");
    const providerPostBody = JSON.parse(String(providerPostCall?.[1]?.body));
    expect(providerPostBody).toMatchObject({
      name: "Local Gemma4",
      provider_type: "ollama",
      base_url: "http://ollama:11434/v1",
      model_identifier: "gemma4:e2b-it-qat",
      embedding_model: "embeddinggemma",
      is_active: true,
    });
    expect(providerPostBody).not.toHaveProperty("api_key");
    expect(container.textContent).toContain("Gemma4 로컬 모델을 등록했습니다");

    const embeddingSaveButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("임베딩 모델 저장"));
    expect(embeddingSaveButton).toBeTruthy();
    await act(async () => {
      embeddingSaveButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    const embeddingPutCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input) === "/api/llm-providers/2" && init?.method === "PUT");
    expect(embeddingPutCall?.[1]?.credentials).toBe("same-origin");
    expect(embeddingPutCall?.[1]?.headers).not.toHaveProperty("Authorization");
    const embeddingPutBody = JSON.parse(String(embeddingPutCall?.[1]?.body));
    expect(embeddingPutBody).toEqual({ embedding_model: "embeddinggemma" });
    expect(container.textContent).toContain("임베딩 모델 지정을 저장했습니다");
  });

  it("renders settings tabs as detail surfaces instead of placeholder dead space", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<SettingsLayout />);
      await Promise.resolve();
      await Promise.resolve();
    });

    for (const tabName of ["멤버", "알림", "자동화", "결제"]) {
      const button = Array.from(container.querySelectorAll("button")).find((candidate) => candidate.textContent === tabName);
      expect(button).toBeTruthy();
      await act(async () => {
        button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        await Promise.resolve();
      });
      expect(container.textContent).toContain(`${tabName === "멤버" ? "멤버와 역할" : tabName === "알림" ? "알림 정책" : tabName === "자동화" ? "자동화 규칙" : "결제와 사용량"}`);
      expect(container.textContent).not.toContain("다음 릴리즈");
    }
  });
});
