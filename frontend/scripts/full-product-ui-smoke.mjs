import { execFile, spawn } from "node:child_process";
import { access, mkdtemp, writeFile } from "node:fs/promises";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { chromium } from "@playwright/test";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const nextCliPath = path.join(frontendDir, "node_modules", "next", "dist", "bin", "next");
const requestedBaseUrl = process.env.NARUON_FULL_PRODUCT_BASE_URL || "http://127.0.0.1:3001";
const requestedScreenshotProfile = resolveFullProductScreenshotProfile();
const SERVER_PROBE_TIMEOUT_MS = 5_000;
const SERVER_READY_TIMEOUT_MS = 90_000;
const IS_WINDOWS = process.platform === "win32";
const DEFAULT_FULL_PRODUCT_SCREENSHOT_PROFILE = "/tmp/naruon-full-product-smoke";
const RESPONSIVE_FULL_PRODUCT_SCREENSHOT_PROFILE = "/tmp/naruon-full-product-responsive-qa";

export const FULL_PRODUCT_ROUTES = [
  { path: "/", name: "home", expectedText: "Naruon" },
  { path: "/mail", name: "mail", expectedText: "메일" },
  { path: "/search", name: "search", expectedText: "맥락 검색" },
  { path: "/calendar", name: "calendar", expectedText: "일정" },
  { path: "/tasks", name: "tasks", expectedText: "작업" },
  { path: "/projects", name: "projects", expectedText: "프로젝트" },
  { path: "/data", name: "data", expectedText: "데이터" },
  { path: "/ai-hub", name: "ai-hub", expectedText: "AI 허브" },
  { path: "/security", name: "security", expectedText: "보안" },
  { path: "/settings", name: "settings", expectedText: "설정" },
];

export const FULL_PRODUCT_VIEWPORTS = [
  { name: "desktop", width: 1440, height: 1024 },
  { name: "mobile", width: 390, height: 844, isMobile: true },
];

export const FULL_PRODUCT_CRITICAL_INTERACTION_ROUTE_NAMES = [
  "mail",
  "search",
  "calendar",
  "tasks",
  "projects",
  "data",
  "ai-hub",
  "security",
  "settings",
];
export const FULL_PRODUCT_CRITICAL_INTERACTION_VIEWPORT_NAMES = ["desktop", "mobile"];
export const FULL_PRODUCT_DESKTOP_INTERACTION_ROUTE_NAMES = FULL_PRODUCT_CRITICAL_INTERACTION_ROUTE_NAMES;
export const FULL_PRODUCT_ACCESSIBILITY_CHECK_NAMES = [
  "visible-duplicate-id",
  "visible-interactive-accessible-name",
  "keyboard-tab-focus-entry",
];

export function resolveFullProductBaseUrl(rawBaseUrl) {
  switch (rawBaseUrl) {
    case "http://127.0.0.1:3001":
    case "http://127.0.0.1:3001/":
      return new URL("http://127.0.0.1:3001");
    case "http://localhost:3001":
    case "http://localhost:3001/":
      return new URL("http://localhost:3001");
    case "http://[::1]:3001":
    case "http://[::1]:3001/":
      return new URL("http://[::1]:3001");
    default:
      throw new Error("Full product smoke must run only against approved localhost targets on port 3001");
  }
}

export function resolveFullProductChromePath(rawChromePath, platform = process.platform) {
  if (rawChromePath !== undefined) {
    switch (rawChromePath) {
      case "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
      case "/usr/bin/google-chrome":
        return "/usr/bin/google-chrome";
      case "/usr/bin/google-chrome-stable":
        return "/usr/bin/google-chrome-stable";
      case "/usr/bin/chromium":
        return "/usr/bin/chromium";
      case "/usr/bin/chromium-browser":
        return "/usr/bin/chromium-browser";
      case "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe":
        return "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
      default:
        throw new Error("PLAYWRIGHT_CHROME_PATH must name an approved Chrome executable");
    }
  }

  if (platform === "darwin") return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  if (platform === "win32") return "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
  return "/usr/bin/google-chrome";
}

export function resolveFullProductScreenshotProfile(environment = process.env) {
  return (
    environment.NARUON_FULL_PRODUCT_SCREENSHOT_PROFILE ??
    environment.NARUON_FULL_PRODUCT_SCREENSHOT_DIR
  );
}

function resolveFullProductArtifactPrefix(rawProfile) {
  switch (rawProfile) {
    case undefined:
    case DEFAULT_FULL_PRODUCT_SCREENSHOT_PROFILE:
      return "naruon-full-product-smoke-";
    case RESPONSIVE_FULL_PRODUCT_SCREENSHOT_PROFILE:
      return "naruon-full-product-responsive-qa-";
    default:
      throw new Error(
        "NARUON_FULL_PRODUCT_SCREENSHOT_PROFILE (or legacy NARUON_FULL_PRODUCT_SCREENSHOT_DIR) must select an approved artifact profile",
      );
  }
}

export async function createFullProductArtifactDirectory(rawProfile) {
  const prefix = resolveFullProductArtifactPrefix(rawProfile);
  return mkdtemp(path.join(tmpdir(), prefix));
}

export function createFullProductServerLaunchSpec(rawBaseUrl) {
  const safeBaseUrl = resolveFullProductBaseUrl(rawBaseUrl);
  return {
    executable: process.execPath,
    args: [nextCliPath, "dev", "--webpack", "--hostname", safeBaseUrl.hostname, "--port", safeBaseUrl.port],
  };
}

export function resolveFullProductArtifactPath(artifactDirectory, fileName) {
  if (!path.isAbsolute(artifactDirectory) || !/^[a-z0-9]+(?:[-.][a-z0-9]+)*\.(?:png|txt)$/u.test(fileName)) {
    throw new Error("Full product smoke artifacts require an absolute directory and a safe file name");
  }
  const artifactPath = path.resolve(artifactDirectory, fileName);
  const relativePath = path.relative(artifactDirectory, artifactPath);
  if (relativePath.startsWith(`..${path.sep}`) || relativePath === ".." || path.isAbsolute(relativePath)) {
    throw new Error("Full product smoke artifact path escaped its private directory");
  }
  return artifactPath;
}

const baseUrl = resolveFullProductBaseUrl(requestedBaseUrl).href;

export function resolveFullProductViewportSpecs(rawViewports = "desktop") {
  const viewportByName = new Map(FULL_PRODUCT_VIEWPORTS.map((viewport) => [viewport.name, viewport]));
  const requestedNames = rawViewports
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  const expandedNames = requestedNames.flatMap((name) => {
    if (name === "all") return FULL_PRODUCT_VIEWPORTS.map((viewport) => viewport.name);
    return [name];
  });
  if (expandedNames.length === 0) {
    throw new Error("At least one full-product viewport is required");
  }

  const seen = new Set();
  return expandedNames.map((name) => {
    const viewport = viewportByName.get(name);
    if (!viewport) {
      throw new Error(`Unknown full-product viewport '${name}'. Expected one of: ${FULL_PRODUCT_VIEWPORTS.map((item) => item.name).join(", ")}`);
    }
    if (seen.has(name)) {
      throw new Error(`Duplicate full-product viewport '${name}'`);
    }
    seen.add(name);
    return viewport;
  });
}

export function fullProductScreenshotName(routeSpec, viewportSpec, viewportCount = 1) {
  const fileName =
    viewportCount === 1 && viewportSpec.name === "desktop"
      ? `${routeSpec.name}.png`
      : `${viewportSpec.name}-${routeSpec.name}.png`;
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*\.png$/u.test(fileName)) {
    throw new Error("Full product screenshot names must contain only lowercase route and viewport segments");
  }
  return fileName;
}

function log(message) {
  process.stdout.write(`${message}\n`);
}

async function captureSmokeScreenshot(page, screenshotPath, label) {
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      await page.screenshot({ path: screenshotPath, fullPage: false });
      return screenshotPath;
    } catch (error) {
      if (attempt < 2) {
        await page.waitForTimeout(250);
        continue;
      }
      const diagnosticFileName = path.basename(screenshotPath).replace(/\.png$/u, ".screenshot-failed.txt");
      const diagnosticPath = resolveFullProductArtifactPath(path.dirname(screenshotPath), diagnosticFileName);
      const reason = error instanceof Error ? error.message : String(error);
      await writeFile(
        diagnosticPath,
        `screenshot_failed label=${label}\nreason=${reason}\n`,
        "utf-8",
      );
      log(`Screenshot capture failed for ${label}: ${reason}`);
      return diagnosticPath;
    }
  }
  return screenshotPath;
}

async function isServerReady(url) {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), SERVER_PROBE_TIMEOUT_MS);
    const response = await fetch(url, { redirect: "manual", signal: controller.signal });
    clearTimeout(timeout);
    return response.status < 500;
  } catch {
    return false;
  }
}

export async function isTcpPortOpen(url) {
  const host = url.hostname.replace(/^\[|\]$/g, "");
  const port = Number(url.port || (url.protocol === "https:" ? 443 : 80));
  if (!Number.isInteger(port) || port <= 0) return false;

  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    const done = (result) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(result);
    };

    socket.setTimeout(1000);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
  });
}

async function waitForServer(url, child) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < SERVER_READY_TIMEOUT_MS) {
    if (child?.exitCode !== null && child?.exitCode !== undefined) {
      throw new Error(`Next dev server exited before becoming ready with code ${child.exitCode}`);
    }
    if (await isServerReady(url)) return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function startServerIfNeeded() {
  if (await isServerReady(baseUrl)) return null;

  const url = new URL(baseUrl);
  if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") {
    throw new Error(`Server is not reachable and cannot be auto-started for non-local URL: ${baseUrl}`);
  }

  if (await isTcpPortOpen(url)) {
    await waitForServer(baseUrl, null);
    return null;
  }

  const launchSpec = createFullProductServerLaunchSpec(baseUrl);
  const child = spawn(
    launchSpec.executable,
    launchSpec.args,
    {
      cwd: frontendDir,
      env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
      stdio: ["ignore", "pipe", "pipe"],
      detached: !IS_WINDOWS,
    },
  );
  child.stdout.on("data", (chunk) => process.stdout.write(chunk));
  child.stderr.on("data", (chunk) => process.stderr.write(chunk));
  try {
    await waitForServer(baseUrl, child);
    return child;
  } catch (error) {
    await stopServerProcess(child);
    throw error;
  }
}

async function stopServerProcess(child) {
  if (!child || child.exitCode !== null) return;

  const waitForExit = new Promise((resolve) => {
    child.once("exit", resolve);
  });
  const timeout = (ms) => new Promise((resolve) => setTimeout(resolve, ms, "timeout"));

  if (IS_WINDOWS) {
    await Promise.race([
      new Promise((resolve) =>
        execFile("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" }).once("close", resolve),
      ),
      timeout(5_000),
    ]);
    await Promise.race([waitForExit, timeout(2_000)]);
    return;
  }

  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }

  if ((await Promise.race([waitForExit, timeout(5_000)])) !== "timeout") return;

  try {
    process.kill(-child.pid, "SIGKILL");
  } catch {
    child.kill("SIGKILL");
  }
  await Promise.race([waitForExit, timeout(2_000)]);
}

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true });
  } catch (error) {
    const fallbackPath = resolveFullProductChromePath(process.env.PLAYWRIGHT_CHROME_PATH);
    await access(fallbackPath);
    log(`Using system Chrome fallback because bundled Playwright browser is unavailable: ${error.message.split("\n")[0]}`);
    return chromium.launch({ headless: true, executablePath: fallbackPath });
  }
}

const sourceEmail = {
  id: 23,
  message_id: "<full-product-smoke@example.com>",
  thread_id: "full-product-thread",
  sender: "pm@example.com",
  recipients: "user@example.com",
  subject: "20B smoke source",
  date: "2026-05-19T09:00:00Z",
  snippet: "20억 판매 검토용 맥락 종합입니다.",
  body: "Private body stays in route mock only.",
  reply_count: 1,
};

const task = {
  id: "task-public-20b",
  title: "20억 판매 검토 실행 항목",
  status: "open",
  priority: "high",
  source_type: "email",
  source_email_id: String(sourceEmail.id),
  related_thread_id: sourceEmail.thread_id,
  updated_at: "2026-07-02T05:00:00Z",
};

const knowledgeTask = {
  id: "task-knowledge-20b",
  title: "나에게 보낸 지식 메모 정리",
  status: "open",
  priority: "normal",
  source_type: "self_sent_knowledge",
  source_email_id: String(sourceEmail.id),
  related_thread_id: sourceEmail.thread_id,
  updated_at: "2026-07-02T05:10:00Z",
};

const webdavTask = {
  id: "task-webdav-evidence-20b",
  title: "첨부파일 WebDAV 폴더 정리",
  status: "in_progress",
  priority: "normal",
  source_type: "webdav",
  source_email_id: String(sourceEmail.id),
  related_thread_id: sourceEmail.thread_id,
  updated_at: "2026-07-02T05:20:00Z",
};

const calendarWritebackSource = {
  source_id: "calendar-source-20b",
  provider: "caldav",
  protocol: "caldav",
  owner_id: "smoke-user",
  organization_id: "org-acme",
  capabilities: ["read", "write", "etag"],
  writeback_enabled: true,
  etag: "calendar-etag-20b",
};

const projectFolder = {
  folder_uid: "project-20b",
  project_name: "Naruon 20B Readiness",
  webdav_path: "/Projects/Naruon_20B_Readiness",
  owner_user_id: "smoke-user",
  organization_id: "org-acme",
};

const webdavAccount = {
  source_id: "webdav-source-20b",
  display_label: "20B readiness WebDAV",
  provider: "webdav",
  protocol: "webdav",
  owner_id: "smoke-user",
  organization_id: "org-acme",
  webdav_path: "/Projects/Naruon_20B_Readiness",
  capabilities: ["read", "write", "etag"],
  writeback_enabled: true,
  etag: "webdav-etag-20b",
};

const aiHubSurface = {
  summary_cards: [
    {
      summary_key: "prompt_templates",
      label_text: "프롬프트",
      value_text: "2",
      detail_text: "원본 근거 템플릿",
      state_code: "ready",
    },
    {
      summary_key: "ai_providers",
      label_text: "판단 보조",
      value_text: "1/1",
      detail_text: "활성 조직 모델 연결",
      state_code: "ready",
    },
  ],
  prompt_cards: [
    {
      prompt_key: "prompt_safe",
      prompt_title: "의사결정 로그 맥락 종합",
      description_text: "메일에서 판단 포인트를 추출합니다.",
      shared_scope: false,
      owner_label: "alice",
      updated_at: "2026-05-29T09:30:00Z",
    },
  ],
  workflow_cards: [
    {
      workflow_key: "workflow_prompt_safe",
      workflow_title: "의사결정 로그 자동 작성",
      trigger_source: "workflow_definition",
      state_code: "ready",
      evidence_text: "2 persisted workflow steps",
    },
  ],
  agent_cards: [
    {
      agent_key: "agent_primary",
      agent_title: "Primary OpenAI",
      model_label: "openai",
      state_code: "active",
      configured: true,
      governance_text: "조직 LLM 모델 연결 registry",
    },
  ],
  evaluation_metrics: [
    {
      metric_key: "provider_readiness",
      metric_label: "Provider 준비도",
      score_value: 100,
      trend_text: "활성 모델 연결 1/1",
    },
  ],
  run_events: [
    {
      event_key: "agent_run_prompt_safe",
      event_title: "워크플로우 실행",
      state_code: "completed",
      evidence_source: "agent_run_records",
      observed_at: "2026-05-29T09:30:00Z",
      detail_text: "3개 판단 포인트를 추출했습니다.",
    },
  ],
};

const securitySurface = {
  scope_kind: "organization",
  viewer: {
    role: "tenant_admin",
    scope_kind: "organization",
  },
  sources: [
    {
      source_type: "webdav_repository",
      source_label: "WebDAV repository",
      scope_kind: "organization",
      capabilities: ["read", "write", "etag"],
      writeback_enabled: true,
      last_observed_at: "2026-05-28T04:00:00Z",
      policy_decision: {
        resource_label: "WebDAV repository",
        resource_type: "webdav_repository",
        allowed: true,
        reason: "allowed",
        evidence_label: "webdav_source_evidence",
      },
    },
  ],
  connector_events: [
    {
      state_code: "heartbeat",
      evidence_label: "connector_observation_evidence",
      observed_at: "2026-05-28T04:00:00Z",
    },
  ],
  durable_audit_events: [
    {
      actor_role: "tenant_admin",
      scope_kind: "organization",
      event_action: "update",
      resource_type: "llm_provider",
      evidence_label: "server_audit_evidence",
      observed_at: "2026-05-28T04:02:00Z",
    },
  ],
  policy_decisions: [
    {
      resource_label: "WebDAV repository",
      resource_type: "webdav_repository",
      allowed: true,
      reason: "allowed",
      evidence_label: "webdav_source_evidence",
    },
    {
      resource_label: "Cross-organization provider secret",
      resource_type: "provider_secret",
      allowed: false,
      reason: "organization_denied",
      evidence_label: "policy_engine_evidence",
    },
  ],
  external_share_reviews: [
    {
      source_type: "webdav_repository",
      review_label: "WebDAV repository writeback boundary",
      exposure_level: "external_writeback",
      decision_reason: "allowed",
    },
  ],
  policy_order: [
    {
      display_name: "Signed session identity",
      evidence_label: "signed_session_evidence",
    },
    {
      display_name: "RBAC allow after ABAC denies",
      evidence_label: "policy_engine_evidence",
    },
  ],
};

const dataQualitySurface = {
  workspace_id: "workspace-org-acme",
  organization_id: "org-acme",
  audit_event: "data.quality_surface.viewed",
  provider_write_executed: false,
  repositories: [
    {
      source_id: "document_repository",
      repository_type: "workspace_document",
      display_name: "20B readiness documents",
      object_count: 2,
      writeback_enabled: null,
      evidence_source: "documents",
      provider_write_executed: false,
    },
  ],
  repository_assets: [
    {
      asset_key: "doc_repository_ready",
      asset_type: "workspace_document",
      display_name: "20b-readiness.md",
      source_label: "Workspace document",
      state_code: "ready",
      detail_text: "document status: uploaded",
      content_chars: 128,
      captured_at: "2026-05-28T05:46:00Z",
      evidence_source: "documents.document_status",
      thread_key: "workspace_document",
      provider_write_executed: false,
    },
  ],
  pipeline_stages: [
    {
      stage_key: "source_registry",
      display_name: "Source registry",
      status_code: "ready",
      progress_percent: 100,
      evidence_source: "webdav_accounts, project_folders",
      detail_text: "2 customer-owned sources are in scope.",
      provider_write_executed: false,
    },
  ],
  embedding_collections: [
    {
      collection_key: "emails_embedding",
      display_name: "Email vectors",
      object_count: 4,
      embedded_count: 3,
      embedding_model: "text-embedding-3-small",
      vector_dimensions: 1536,
      status_code: "running",
      evidence_source: "emails.embedding",
      provider_write_executed: false,
    },
  ],
  quality_checks: [
    {
      check_key: "thread_id_integrity",
      display_name: "Thread id integrity",
      status_code: "ready",
      issue_count: 0,
      total_count: 4,
      evidence_source: "emails.thread_id",
      detail_text: "Scoped emails have canonical thread ids.",
      provider_write_executed: false,
    },
  ],
  connector_events: [
    {
      event_uid: "connector_evt_data_quality",
      signal_key: "connector_heartbeat",
      state_code: "heartbeat",
      detail_text: "outbound connector heartbeat received",
      observed_at: "2026-05-28T05:45:00Z",
    },
  ],
};

const dataEvidenceSnapshot = {
  snapshot_version: "data_quality_evidence_snapshot.v1",
  generated_at: "2026-05-28T05:47:00Z",
  audit_event: "data.quality_surface.evidence_snapshot.viewed",
  scope_label: "full_product_smoke",
  snapshot_digest: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  digest_algorithm: "sha256",
  canonical_payload_fields: [],
  privacy_redaction_policy: {
    raw_content_exposed: false,
    stable_identifiers_exposed: false,
    provider_credentials_exposed: false,
    redacted_fields: [],
    allowed_sample_fields: [],
  },
  validation_status: {
    status_code: "ready",
    display_name: "Ready",
    detail_text: "Smoke evidence snapshot is redacted and verifier-ready.",
    provider_write_executed: false,
  },
  verification_handoff: {
    handoff_text: "Verify the copied smoke snapshot JSON before sharing diligence materials.",
    verifier_command: "python scripts/verify_evidence_snapshot.py snapshot.json",
    accepted_input: "data_quality_evidence_snapshot.v1 JSON",
    digest_algorithm: "sha256",
    excluded_digest_fields: ["snapshot_digest"],
    success_exit_code: 0,
    failure_exit_codes: { invalid_digest: 2 },
    provider_write_executed: false,
  },
  parser_manifest_summary: [],
  content_graph_evidence_samples: [],
  knowledge_graph_evidence_samples: [],
  evidence_packet_checklist: [],
  data_room_package_manifest: [],
  diligence_exception_register: [],
  diligence_risk_matrix: [],
  diligence_close_artifact_review_queue: [],
  diligence_close_owner_handoff_queue: [],
  diligence_close_traceability_map: [],
  diligence_close_decision_summary: null,
  diligence_close_proof_plan: [],
};

const accountConfig = {
  user_id: "smoke-user",
  smtp_server: null,
  smtp_port: null,
  smtp_username: null,
  has_smtp_password: false,
  imap_server: null,
  imap_port: null,
  imap_username: null,
  has_imap_password: false,
  pop3_server: null,
  pop3_port: null,
  pop3_username: null,
  has_pop3_password: false,
  oauth_client_id: null,
  oauth_redirect_uri: null,
  has_oauth_client_secret: false,
};

const llmProvider = {
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
};

const runnerConfig = {
  workspace_id: "workspace-org-acme",
  configured: true,
  fingerprint: "runner-smoke",
  updated_at: "2026-05-28T05:45:00Z",
  connector_manifest: {
    role: "outbound_connector",
    network_mode: "outbound_only",
    control_plane_domain: "naruon.net",
    local_protocols: ["imap", "smtp", "caldav", "webdav"],
    prohibited_roles: ["mailbox_host", "mx_server"],
    runner_usage: "customer_owned_connector",
  },
};

const operationalSignals = {
  workspace_id: "workspace-org-acme",
  audit_event: "observability.operational_signals.viewed",
  telemetry: {
    prometheus_metrics_enabled: true,
    otel_traces_enabled: true,
    otel_endpoint_configured: true,
    otel_endpoint_host: "otel.example.com",
  },
  connector: {
    workspace_id: "workspace-org-acme",
    registration_state: "registration_configured",
    connection_state: "connected",
    active_connection_count: 1,
    control_plane_domain: "naruon.net",
    network_mode: "outbound_only",
    runner_usage: "customer_owned_connector",
    local_protocols: ["imap", "smtp", "caldav", "webdav"],
    last_heartbeat_at: "2026-05-28T05:45:00Z",
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
  signals: [
    {
      signal_key: "frontend",
      display_name: "Frontend health",
      state: "ready",
      evidence_source: "full-product-smoke",
      detail: "Route rendered",
      provider_write_executed: false,
    },
  ],
};

function routeJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installRoutes(page) {
  let emailSendCount = 0;
  let savedAccountConfig = { ...accountConfig };
  let savedLlmProviders = [{ ...llmProvider }];

  await page.route("**/auth/session", (route) => routeJson(route, {
    claims: {
      userId: "smoke-user",
      organizationId: "org-acme",
      workspaceId: "workspace-org-acme",
    },
  }));
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const endpoint = new URL(request.url()).pathname;

    if (endpoint === "/api/emails") return routeJson(route, { emails: [sourceEmail] });
    if (endpoint === "/api/emails/pending-replies") return routeJson(route, { emails: [sourceEmail] });
    if (endpoint === "/api/emails/23") return routeJson(route, sourceEmail);
    if (endpoint === "/api/emails/thread/full-product-thread") return routeJson(route, { thread: [sourceEmail] });
    if (endpoint === "/api/search") {
      return routeJson(route, {
        results: [
          {
            id: 202,
            source_message_id: "<full-product-smoke@example.com>",
            subject: "20B readiness result",
            sender: "pm@example.com",
            date: "2026-05-20T09:00:00Z",
            snippet: "맥락 검색 결과에서 관계 캡처 액션을 실행할 수 있습니다.",
            thread_id: "full-product-thread",
            reply_count: 1,
            score: 0.93,
          },
        ],
      });
    }
    if (endpoint === "/api/llm/summarize") return routeJson(route, { summary: "20억 판매 검토용 맥락 종합입니다.", action_items: ["근거 확인"], confidence: 0.86 });
    if (endpoint === "/api/llm/draft") return routeJson(route, { draft: "검토 가능한 답장 초안입니다." });
    if (endpoint === "/api/llm/translate") return routeJson(route, { translation: "번역된 맥락입니다." });
    if (endpoint === "/api/emails/send") {
      emailSendCount += 1;
      return routeJson(route, { simulated: emailSendCount === 1 });
    }
    if (endpoint === "/api/tasks") return routeJson(route, [task, knowledgeTask, webdavTask]);
    if (endpoint === "/api/tasks/from-email") return routeJson(route, { created: 1 });
    if (endpoint === "/api/tasks/reply-sla-escalations") {
      return routeJson(route, {
        evaluated: 1,
        created: 1,
        policy: { overdue_hours: 48 },
        tasks: [task, knowledgeTask, webdavTask],
      });
    }
    if (endpoint.startsWith("/api/tasks/")) {
      const targetTask = [task, knowledgeTask, webdavTask].find((candidate) => endpoint.includes(candidate.id)) ?? task;
      return routeJson(route, { ...targetTask, status: "done" });
    }
    if (endpoint === "/api/calendar/writeback-sources") return routeJson(route, [calendarWritebackSource]);
    if (endpoint === "/api/calendar/writeback-intent") {
      let requestBody = {};
      try {
        requestBody = request.postDataJSON();
      } catch {
        requestBody = {};
      }
      const executeProvider = requestBody.execute_provider === true;
      return routeJson(route, {
        workspace_id: "workspace-org-acme",
        target_source_id: calendarWritebackSource.source_id,
        protocol: calendarWritebackSource.protocol,
        writeback_mode: "customer_owned",
        requires_if_match: true,
        if_match: calendarWritebackSource.etag,
        provenance: { source: "full-product-smoke" },
        audit_event: executeProvider ? "calendar.writeback.executed" : "calendar.writeback_intent.created",
        provider_write_executed: executeProvider,
        status: executeProvider ? "executed" : "intent_ready",
        runner_request_id: executeProvider ? "runner-calendar-20b" : null,
        provider_status: executeProvider ? 204 : null,
        error_code: null,
        retry_item_uid: null,
      });
    }
    if (endpoint === "/api/webdav/folders") return routeJson(route, [projectFolder]);
    if (endpoint === "/api/webdav/accounts") return routeJson(route, [webdavAccount]);
    if (endpoint === "/api/webdav/writeback-intent") {
      return routeJson(route, {
        intent: "writeback",
        source_id: webdavAccount.source_id,
        target_label: webdavAccount.display_label,
        requires_if_match: true,
        if_match: webdavAccount.etag,
        provenance: "server-authoritative",
        audit_event: "webdav.writeback_intent.created",
        provider_write_executed: false,
      });
    }
    if (endpoint === "/api/webdav/knowledge-materialization-intent") {
      let requestBody = {};
      try {
        requestBody = request.postDataJSON();
      } catch {
        requestBody = {};
      }
      const executeProvider = requestBody.execute_provider === true;
      return routeJson(route, {
        intent: "knowledge_materialization",
        status: executeProvider ? "executed" : "intent_ready",
        task_id: requestBody.source_task_id ?? knowledgeTask.id,
        source_type: "self_sent_knowledge",
        source_email_id: knowledgeTask.source_email_id,
        source_thread_id: knowledgeTask.related_thread_id,
        source_id: webdavAccount.source_id,
        target_label: webdavAccount.display_label,
        target_path: "/Projects/Naruon_20B_Readiness/knowledge-note.md",
        requires_if_match: true,
        provenance: "server-authoritative",
        provider_write_executed: executeProvider,
        audit_event: executeProvider ? "webdav.knowledge_materialization.executed" : "webdav.knowledge_materialization_intent.created",
        runner_request_id: executeProvider ? "runner-knowledge-20b" : null,
        provider_status: executeProvider ? 201 : null,
        error_code: null,
        retry_item_uid: null,
      });
    }
    if (endpoint === "/api/data/quality-surface") return routeJson(route, dataQualitySurface);
    if (endpoint === "/api/data/quality-surface/evidence-snapshot") return routeJson(route, dataEvidenceSnapshot);
    if (endpoint === "/api/data/documents") return routeJson(route, { document_id: "doc-smoke", status: "stored" });
    if (endpoint === "/api/data/documents/doc_repository_ready/embedding-regeneration-intent") {
      return routeJson(route, {
        action_id: "doc-embedding-smoke",
        document_name: "20b-readiness.md",
        message: "Embedding regeneration intent recorded; no provider write executed.",
        provider_write_executed: false,
      });
    }
    if (endpoint === "/api/data/documents/doc_repository_ready/hwp-conversion-intent") {
      return routeJson(route, {
        action_id: "doc-hwp-smoke",
        document_name: "20b-readiness.md",
        message: "HWP conversion intent recorded; no provider write executed.",
        provider_write_executed: false,
      });
    }
    if (endpoint === "/api/data/documents/doc_repository_ready/webdav-materialization-intent") {
      return routeJson(route, {
        action_id: "doc-webdav-smoke",
        document_name: "20b-readiness.md",
        message: "WebDAV materialization executed by the connector.",
        provider_write_executed: true,
      });
    }
    if (endpoint.startsWith("/api/data/documents/")) return routeJson(route, { action_id: "doc-action-smoke", status: "accepted" });
    if (endpoint === "/api/emails/unique-thread-intent") {
      return routeJson(route, {
        status: "intent_ready",
        candidates_checked: 2,
        duplicates_found: 2,
        provider_write_executed: false,
        provenance: "server-authoritative",
        audit_event: "email.unique_thread_intent.created",
        thread_updates: [
          {
            candidate_key: "full-product-smoke-message-id",
            canonical_thread_id: "full-product-thread",
            dedupe_key: "full-product-smoke@example.com",
            match_reason: "message_id",
            existing_message_id: "full-product-smoke@example.com",
          },
        ],
      });
    }
    if (endpoint === "/api/ai-hub/surface") return routeJson(route, aiHubSurface);
    if (endpoint === "/api/security/access-surface") return routeJson(route, securitySurface);
    if (endpoint === "/api/security/permission-change-intent") {
      let requestBody = {};
      try {
        requestBody = request.postDataJSON();
      } catch {
        requestBody = {};
      }
      const reasonByDecision = {
        allow_writeback: "allowed",
        deny_external_write: "organization_denied",
        deny_workspace_write: "workspace_denied",
        deny_region_export: "data_region_denied",
        deny_missing_consent: "consent_denied",
      };
      const allowed = requestBody.decision === "allow_writeback";
      return routeJson(route, {
        decision: requestBody.decision ?? "deny_external_write",
        resource_type: requestBody.resource_type ?? "provider_secret",
        allowed,
        reason: reasonByDecision[requestBody.decision] ?? "organization_denied",
        evidence_label: "policy_engine_evidence",
        audit_event: "security.permission_change_intent",
        provider_write_executed: false,
        denial_result: allowed ? "approval_required_before_external_write" : "provider_denied_by_policy",
        observed_at: "2026-05-28T04:05:00Z",
      });
    }
    if (endpoint === "/api/accounts/config") {
      if (request.method() === "PUT") {
        let requestBody = {};
        try {
          requestBody = request.postDataJSON();
        } catch {
          requestBody = {};
        }
        savedAccountConfig = {
          ...savedAccountConfig,
          smtp_server: requestBody.smtp_server ?? null,
          smtp_port: requestBody.smtp_port ?? null,
          smtp_username: requestBody.smtp_username ?? null,
          has_smtp_password: Boolean(requestBody.smtp_password) || savedAccountConfig.has_smtp_password,
          imap_server: requestBody.imap_server ?? null,
          imap_port: requestBody.imap_port ?? null,
          imap_username: requestBody.imap_username ?? null,
          has_imap_password: Boolean(requestBody.imap_password) || savedAccountConfig.has_imap_password,
          pop3_server: requestBody.pop3_server ?? null,
          pop3_port: requestBody.pop3_port ?? null,
          pop3_username: requestBody.pop3_username ?? null,
          has_pop3_password: Boolean(requestBody.pop3_password) || savedAccountConfig.has_pop3_password,
          oauth_client_id: requestBody.oauth_client_id ?? null,
          oauth_redirect_uri: requestBody.oauth_redirect_uri ?? null,
          has_oauth_client_secret: Boolean(requestBody.oauth_client_secret) || savedAccountConfig.has_oauth_client_secret,
        };
      }
      return routeJson(route, savedAccountConfig);
    }
    if (endpoint === "/api/llm-providers" && request.method() === "POST") {
      let requestBody = {};
      try {
        requestBody = request.postDataJSON();
      } catch {
        requestBody = {};
      }
      const createdProvider = {
        ...llmProvider,
        id: 2,
        name: requestBody.name ?? "Local Gemma4",
        provider_type: requestBody.provider_type ?? "ollama",
        base_url: requestBody.base_url ?? "http://ollama:11434/v1",
        model_identifier: requestBody.model_identifier ?? "gemma4:e2b-it-qat",
        embedding_model: requestBody.embedding_model ?? "embeddinggemma",
        fingerprint: null,
        updated_at: "2026-07-02T05:30:00Z",
      };
      savedLlmProviders = [createdProvider, ...savedLlmProviders.filter((provider) => provider.id !== createdProvider.id)];
      return routeJson(route, createdProvider);
    }
    if (endpoint === "/api/llm-providers") return routeJson(route, savedLlmProviders);
    if (endpoint.startsWith("/api/llm-providers/")) {
      let requestBody = {};
      try {
        requestBody = request.postDataJSON();
      } catch {
        requestBody = {};
      }
      const providerId = Number.parseInt(endpoint.split("/").at(-1) ?? "", 10);
      const currentProvider = savedLlmProviders.find((provider) => provider.id === providerId) ?? llmProvider;
      const updatedProvider = {
        ...currentProvider,
        embedding_model: requestBody.embedding_model ?? llmProvider.embedding_model,
        updated_at: "2026-07-02T05:31:00Z",
      };
      savedLlmProviders = savedLlmProviders.map((provider) => (provider.id === updatedProvider.id ? updatedProvider : provider));
      return routeJson(route, updatedProvider);
    }
    if (endpoint === "/api/runner-config") return routeJson(route, runnerConfig);
    if (endpoint === "/api/runner-config/rotate") return routeJson(route, runnerConfig);
    if (endpoint === "/api/observability/operational-signals") return routeJson(route, operationalSignals);
    if (endpoint === "/api/network/graph") {
      return routeJson(route, {
        nodes: [
          { id: "sender-pm", label: "PM 김지현", title: "계약 검토 담당자" },
          { id: "thread-20b", label: "20B readiness thread", title: "구매 검토 메일 스레드" },
          { id: "calendar-review", label: "이사회 일정", title: "CalDAV writeback 후보" },
        ],
        edges: [
          { source: "sender-pm", target: "thread-20b", weight: 2, title: "메일 2건" },
          { source: "thread-20b", target: "calendar-review", weight: 1, title: "일정 후보 1건" },
        ],
      });
    }
    if (endpoint === "/api/ontology/relationships") return routeJson(route, []);
    if (endpoint === "/api/ontology/relationships/capture-source") {
      return routeJson(route, {
        sender_email: "pm@example.com",
        parent_sender_email: null,
        source_message_id: "<full-product-smoke@example.com>",
        source_thread_id: "full-product-thread",
        relationship_type: "sender_context",
        confidence_score: 0.91,
        next_action: "계약 검토 담당자를 확인합니다.",
        action_reason: "검색 결과 원본 메시지의 후속 조치입니다.",
      });
    }
    if (endpoint === "/api/tools") return routeJson(route, []);
    if (endpoint.startsWith("/api/tools/")) return routeJson(route, { output: "ok", status: "success" });
    if (endpoint === "/api/runtime-config") return routeJson(route, {});

    return routeJson(route, { ok: true });
  });
}

async function runCriticalInteractionSmoke(page, routeSpec, viewportSpec) {
  if (!FULL_PRODUCT_CRITICAL_INTERACTION_ROUTE_NAMES.includes(routeSpec.name)) return [];
  const evidence = (name) => `${viewportSpec.name}:${name}`;

  if (routeSpec.name === "mail") {
    await page.getByText("20B smoke source", { exact: true }).first().click();
    const sourceDrawerTrigger = page.getByRole("button", { name: "근거 원본 보기", exact: true });
    await sourceDrawerTrigger.click();
    const sourceDrawer = page.getByRole("dialog", { name: "맥락 종합 근거", exact: true });
    await sourceDrawer.waitFor({ state: "visible", timeout: 10_000 });
    await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "근거 원본 닫기");
    const closeSourceDrawerButton = sourceDrawer.getByRole("button", { name: "근거 원본 닫기", exact: true });
    const openOriginalButton = sourceDrawer.getByRole("button", { name: "스레드 원문으로 이동", exact: true });
    await openOriginalButton.focus();
    await page.keyboard.press("Tab");
    await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "근거 원본 닫기");
    await closeSourceDrawerButton.focus();
    await page.keyboard.press("Shift+Tab");
    await page.waitForFunction(() => document.activeElement?.textContent?.replace(/\s+/g, " ").trim() === "스레드 원문으로 이동");
    await page.keyboard.press("Escape");
    await sourceDrawer.waitFor({ state: "hidden", timeout: 10_000 });
    await page.waitForFunction(() => document.activeElement?.textContent?.replace(/\s+/g, " ").trim() === "근거 원본 보기");
    await page.getByRole("button", { name: "답장 초안 생성", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#reply-draft")?.value.includes("검토 가능한 답장 초안입니다."));
    await page.getByRole("button", { name: "답장 보내기", exact: true }).click();
    await page.getByText("개발 모드에서 답장을 시뮬레이션했습니다. 실제 메일은 전송되지 않았습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "답장 초안 생성", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#reply-draft")?.value.includes("검토 가능한 답장 초안입니다."));
    await page.getByRole("button", { name: "답장 보내기", exact: true }).click();
    await page.getByText("답장을 전송했습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    const createTaskButton = page.getByRole("button", { name: "실행 항목 생성" }).first();
    await createTaskButton.waitFor({ state: "visible", timeout: 10_000 });
    await createTaskButton.click();
    await page.getByText("1개 실행 항목을 티켓형 실행 항목으로 추적합니다.").waitFor({ state: "visible", timeout: 10_000 });
    return [
      evidence("mail:select-message"),
      evidence("mail:open-source-drawer"),
      evidence("mail:verify-source-drawer-initial-focus"),
      evidence("mail:verify-source-drawer-tab-trap"),
      evidence("mail:verify-source-drawer-escape-close"),
      evidence("mail:verify-source-drawer-focus-restore"),
      evidence("mail:generate-reply-draft"),
      evidence("mail:send-simulated-reply"),
      evidence("mail:send-provider-reply"),
      evidence("mail:create-source-linked-task"),
    ];
  }

  if (routeSpec.name === "search") {
    await page.getByText("20B readiness result", { exact: true }).first().waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "관계 원본", exact: true }).click();
    await page.getByText("원본 메시지 필터로 관계 API를 조회합니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "판단 보조", exact: true }).click();
    await page.getByText("외부 실행은 사용자가 메일, 일정, 관계 캡처 액션을 명시적으로 선택할 때만 진행됩니다.", { exact: false }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "관계 캡처", exact: true }).click();
    await page.getByText("계약 검토 담당자를 확인합니다.").waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "관계 원본", exact: true }).click();
    await page.getByText("1개 관계 연결", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("heading", { name: "관계 맥락과 타임라인", exact: true }).scrollIntoViewIfNeeded();
    await page.getByText("3개 노드와 2개 관계가 이 스레드 맥락에 연결되어 있습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("관련 노드: PM 김지현, 20B readiness thread, 이사회 일정", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.locator('[aria-label="3개 노드와 2개 관계가 있는 관계 맥락"]').waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "첫 관계 보기", exact: true }).click();
    await page.getByText("선택된 관계: PM 김지현 -> 20B readiness thread (메일 2건)", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("첫 관계를 선택했습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "그래프 확대", exact: true }).click();
    await page.getByText("그래프 확대 완료", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "전체 그래프 맞춤", exact: true }).click();
    await page.getByText("그래프 맞춤 완료", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByLabel("관계 선택", { exact: true }).selectOption({ label: "관계 2: 20B readiness thread -> 이사회 일정 (일정 후보 1건)" });
    await page.getByText("선택된 관계: 20B readiness thread -> 이사회 일정 (일정 후보 1건)", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("선택한 관계를 열었습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByLabel("노드 선택", { exact: true }).selectOption({ label: "노드: 이사회 일정" });
    await page.getByText("선택된 노드: 이사회 일정", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("선택한 노드를 열었습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("선택된 노드: 이사회 일정", { exact: true }).scrollIntoViewIfNeeded();
    return [
      evidence("search:select-result"),
      evidence("search:open-source-evidence-tab"),
      evidence("search:open-decision-assist-tab"),
      evidence("search:capture-sender-relationship"),
      evidence("search:verify-captured-relationship-state"),
      evidence("search:open-network-graph"),
      evidence("search:verify-network-graph-summary"),
      evidence("search:verify-network-graph-canvas-label"),
      evidence("search:select-network-relationship"),
      evidence("search:verify-network-relationship-detail"),
      evidence("search:zoom-network-graph"),
      evidence("search:fit-network-graph"),
      evidence("search:select-network-second-relationship"),
      evidence("search:verify-network-node-detail"),
    ];
  }

  if (routeSpec.name === "calendar") {
    await page.getByRole("button", { name: "새 일정 intent 점검", exact: true }).click();
    await page.getByText("기록됨", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "ETag 업데이트 점검", exact: true }).click();
    await page.getByText("If-Match 필요", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "ETag 실행 요청", exact: true }).click();
    await page.getByText("외부 원본 쓰기 완료", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("재시도 없음", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    return [
      evidence("calendar:create-writeback-intent"),
      evidence("calendar:verify-etag-update-intent"),
      evidence("calendar:request-provider-write"),
      evidence("calendar:verify-provider-completion-state"),
      evidence("calendar:verify-provider-no-retry-state"),
    ];
  }

  if (routeSpec.name === "tasks") {
    await page.getByRole("button", { name: "보낸 메일 미답변 팔로업 작업 생성" }).click();
    await page.getByText("미답변 팔로업 결과가 보드에 반영되었습니다.").waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "20억 판매 검토 실행 항목 상태를 완료로 변경", exact: true }).click();
    await page.getByText("20억 판매 검토 실행 항목 상태를 완료로 변경했습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "나에게 보낸 지식 메모 정리 WebDAV 지식 노트 의도 생성", exact: true }).click();
    await page.getByText("WebDAV/Notes 의도 준비", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "나에게 보낸 지식 메모 정리 WebDAV 지식 노트 실행 요청", exact: true }).click();
    await page.getByText("외부 쓰기 실행됨", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("재시도 없음", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    return [
      evidence("tasks:create-reply-sla-followup"),
      evidence("tasks:complete-source-linked-task"),
      evidence("tasks:create-knowledge-webdav-intent"),
      evidence("tasks:request-knowledge-provider-write"),
      evidence("tasks:verify-knowledge-provider-completion-state"),
      evidence("tasks:verify-knowledge-provider-no-retry-state"),
    ];
  }

  if (routeSpec.name === "projects") {
    const projectContent = page.getByRole("region", { name: "프로젝트 내용" });
    await page.getByRole("link", { name: "관련 문서/메일 연결", exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "프로젝트 의사결정 추가" }).first().click();
    await projectContent.getByText("작업 흐름 반영", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await projectContent.getByText("근거: WebDAV 폴더", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "프로젝트 상세 열기", exact: true }).click();
    await projectContent.getByText("프로젝트 개요", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await projectContent.getByText("저장소 경계 확인됨", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await projectContent.getByText("WebDAV 폴더 근거", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await projectContent.getByText("스레드 근거 연결됨", { exact: true }).first().waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("region", { name: "프로젝트 작업 목록" }).getByText("문서 근거", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    const evidenceEditor = page.getByRole("region", { name: "프로젝트 근거 편집" });
    await evidenceEditor.getByLabel("프로젝트 근거 메모", { exact: true }).fill("20B 구매 심사용 WebDAV 경계와 이사회 승인 근거를 함께 저장합니다.");
    await evidenceEditor.getByLabel("연결 원본 변경", { exact: true }).selectOption({ label: "문서 근거" });
    await evidenceEditor.getByRole("button", { name: "근거 저장", exact: true }).click();
    await evidenceEditor.getByText("프로젝트 근거가 저장되었습니다: 문서 근거", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await evidenceEditor.getByText("20B 구매 심사용 WebDAV 경계와 이사회 승인 근거를 함께 저장합니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    const connectedResources = page.getByRole("region", { name: "연결된 자원" });
    await connectedResources.getByText("원본 종류", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await connectedResources.locator("li").filter({ hasText: "원본 종류" }).getByText("3", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    return [
      evidence("projects:open-related-source-link"),
      evidence("projects:open-decision-log"),
      evidence("projects:verify-webdav-folder-evidence"),
      evidence("projects:reopen-project-detail"),
      evidence("projects:verify-source-boundary"),
      evidence("projects:verify-thread-source-attachment"),
      evidence("projects:verify-document-source-attachment"),
      evidence("projects:edit-evidence-note"),
      evidence("projects:mutate-evidence-source"),
      evidence("projects:save-evidence-note"),
      evidence("projects:verify-evidence-save-state"),
      evidence("projects:verify-source-type-count"),
    ];
  }

  if (routeSpec.name === "data") {
    await page.getByRole("button", { name: "임베딩 재생성 의도", exact: true }).click();
    await page.getByText("Embedding regeneration intent recorded", { exact: false }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "HWP 변환 의도", exact: true }).click();
    await page.getByText("HWP conversion intent recorded", { exact: false }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "WebDAV 문서 실행 요청", exact: true }).click();
    await page.getByText("WebDAV materialization executed by the connector.", { exact: false }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("외부 쓰기 실행됨", { exact: false }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "WebDAV 반영 의도 점검", exact: true }).click();
    await page.getByText("원본 반영 의도", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("If-Match 필요", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "중복 메일 스레드 의도 점검", exact: true }).click();
    await page.getByText("Message-ID 근거", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "품질 점검", exact: true }).click();
    await page.getByRole("heading", { name: "Thread id integrity", exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    return [
      evidence("data:create-embedding-regeneration-intent"),
      evidence("data:create-hwp-conversion-intent"),
      evidence("data:execute-webdav-materialization"),
      evidence("data:verify-webdav-materialization-completion-state"),
      evidence("data:create-webdav-writeback-intent"),
      evidence("data:create-unique-thread-intent"),
      evidence("data:open-quality-checks"),
    ];
  }

  if (routeSpec.name === "ai-hub") {
    const activeAiHubPanel = page.locator('[role="tabpanel"]');
    await page.getByRole("tab", { name: "워크플로우", exact: true }).click();
    await activeAiHubPanel.getByText("의사결정 로그 자동 작성", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "평가", exact: true }).click();
    await activeAiHubPanel.getByText("연동 준비도", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "평가 근거 보기", exact: true }).first().click();
    await page.getByRole("tab", { name: "실행 이력", exact: true }).click();
    const runEvent = activeAiHubPanel.locator("article").filter({ hasText: "워크플로우 실행" }).first();
    await runEvent.getByText("워크플로우 실행", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await runEvent.getByText("완료", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await runEvent.getByText("3개 판단 포인트를 추출했습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await runEvent.getByText("agent_run_records", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    return [
      evidence("ai-hub:open-workflow-tab"),
      evidence("ai-hub:open-evaluation-tab"),
      evidence("ai-hub:open-run-history-from-evidence"),
      evidence("ai-hub:open-run-history"),
      evidence("ai-hub:verify-run-event-title"),
      evidence("ai-hub:verify-run-event-completion-state"),
      evidence("ai-hub:verify-run-event-detail"),
      evidence("ai-hub:verify-run-event-evidence-source"),
    ];
  }

  if (routeSpec.name === "security") {
    const accessRegion = page.getByRole("region", { name: "접근 권한 소스 거버넌스", exact: true });
    await accessRegion.getByRole("heading", { name: "원본 연결 RBAC / ABAC", exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    const sourceGovernance = viewportSpec.name === "mobile"
      ? accessRegion.locator("article").filter({ hasText: "WebDAV 저장소 1" }).first()
      : accessRegion.locator("tbody tr").filter({ hasText: "WebDAV 저장소 1" }).first();
    await sourceGovernance.getByText("WebDAV 저장소 1", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await sourceGovernance.getByText("조직 스코프", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await sourceGovernance.getByText("쓰기", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    if (viewportSpec.name !== "mobile") {
    await sourceGovernance.getByText("쓰기 의도 가능", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    }
    await sourceGovernance.getByText("충돌 검사", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await sourceGovernance.getByText("허용", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    const permissionEditor = page.getByRole("region", { name: "보안 권한 편집", exact: true });
    await permissionEditor.getByLabel("권한 판정 변경", { exact: true }).selectOption({ label: "외부 쓰기 차단" });
    await permissionEditor.getByText("조직 차단 - 외부 쓰기 실행 안 함", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByRole("button", { name: "권한 저장", exact: true }).click();
    await permissionEditor.getByText("권한 변경이 저장되었습니다: 외부 쓰기 차단", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByText("security.permission_change_intent", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByText("실행 안 함", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByLabel("권한 판정 변경", { exact: true }).selectOption({ label: "워크스페이스 밖 쓰기 차단" });
    await permissionEditor.getByText("워크스페이스 차단 - 외부 쓰기 실행 안 함", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByRole("button", { name: "권한 저장", exact: true }).click();
    await permissionEditor.getByText("워크스페이스 차단", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByLabel("권한 판정 변경", { exact: true }).selectOption({ label: "리전 외부 내보내기 차단" });
    await permissionEditor.getByText("리전 차단 - 외부 쓰기 실행 안 함", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByRole("button", { name: "권한 저장", exact: true }).click();
    await permissionEditor.getByText("리전 차단", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByText("데이터 내보내기", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByLabel("권한 판정 변경", { exact: true }).selectOption({ label: "동의 없는 CalDAV 쓰기 차단" });
    await permissionEditor.getByText("동의 차단 - 외부 쓰기 실행 안 함", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await permissionEditor.getByRole("button", { name: "권한 저장", exact: true }).click();
    await permissionEditor.getByText("동의 차단", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "감사 로그", exact: true }).click();
    const auditRegion = page.getByRole("region", { name: "보안 감사 로그", exact: true });
    await auditRegion.getByText("지속 감사 근거", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await auditRegion.getByText("설정 변경 / LLM 제공자", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await auditRegion.getByText("서버 감사 로그", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await auditRegion.getByText("서버 근거", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await auditRegion.getByText("하트비트 수신", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await auditRegion.getByText("connector 관측 근거", { exact: false }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "외부 공유", exact: true }).click();
    await page.getByText("외부 공유 / 쓰기 경계", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("외부 쓰기 실행 안 함", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "정책", exact: true }).click();
    await page.getByText("차단 우선 정책 순서", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("교차 조직 제공자 secret", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("조직 차단", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("tab", { name: "접근 권한", exact: true }).click();
    const finalPermissionEditor = page.getByRole("region", { name: "보안 권한 편집", exact: true });
    await finalPermissionEditor.getByLabel("권한 판정 변경", { exact: true }).selectOption({ label: "외부 쓰기 차단" });
    await finalPermissionEditor.getByRole("button", { name: "권한 저장", exact: true }).click();
    await finalPermissionEditor.scrollIntoViewIfNeeded();
    await finalPermissionEditor.getByText("권한 변경이 저장되었습니다: 외부 쓰기 차단", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await finalPermissionEditor.getByText("security.permission_change_intent", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    return [
      evidence("security:verify-access-source-governance"),
      evidence("security:verify-write-capability-boundary"),
      evidence("security:verify-policy-allow-decision"),
      evidence("security:edit-permission-decision"),
      evidence("security:save-permission-decision"),
      evidence("security:verify-denial-result-state"),
      evidence("security:verify-permission-save-server-evidence"),
      evidence("security:verify-permission-workspace-denial"),
      evidence("security:verify-permission-region-denial"),
      evidence("security:verify-permission-consent-denial"),
      evidence("security:return-permission-editor-evidence"),
      evidence("security:open-audit-log"),
      evidence("security:verify-durable-audit-event"),
      evidence("security:verify-connector-observation"),
      evidence("security:open-sharing-review"),
      evidence("security:verify-external-write-block"),
      evidence("security:open-policy-order"),
      evidence("security:verify-deny-sample"),
    ];
  }

  if (routeSpec.name === "settings") {
    await page.getByRole("button", { name: "AI 모델", exact: true }).click();
    await page.getByText("/api/llm-providers", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("heading", { name: "Primary OpenAI", exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("radio", { name: /text-embedding-3-large/ }).check();
    await page.getByRole("button", { name: "임베딩 모델 저장", exact: true }).click();
    await page.getByText("임베딩 모델 지정을 저장했습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("region", { name: "등록된 AI 모델", exact: true }).getByText("text-embedding-3-large", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "연결 계정", exact: true }).click();
    await page.locator("#smtp-server").fill("smtp.20b.example.com");
    await page.locator("#smtp-port").fill("587");
    await page.locator("#smtp-username").fill("pilot.sender@20b.example.com");
    await page.locator("#smtp-password").fill("smoke-secret-only");
    await page.getByRole("button", { name: "계정 설정 저장", exact: true }).click();
    await page.getByText("계정 설정을 저장했습니다. 저장된 secret은 응답에 노출되지 않습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("smtp.20b.example.com:587", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("pilot.sender@20b.example.com", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("저장된 secret 유지", { exact: true }).first().waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "워크스페이스", exact: true }).click();
    const calendarStartupButton = page.locator("button").filter({ hasText: "일정 관리" }).last();
    await calendarStartupButton.click();
    const calendarStartupClass = await calendarStartupButton.getAttribute("class");
    if (!calendarStartupClass?.includes("border-primary")) {
      throw new Error("Settings startup view selector did not mark the calendar option as active");
    }
    await page.reload({ waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "워크스페이스 설정", exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    const persistedCalendarStartupButton = page.locator("button").filter({ hasText: "일정 관리" }).last();
    await persistedCalendarStartupButton.waitFor({ state: "visible", timeout: 10_000 });
    const persistedCalendarStartupClass = await persistedCalendarStartupButton.getAttribute("class");
    if (!persistedCalendarStartupClass?.includes("border-primary")) {
      throw new Error("Settings startup view selector did not persist the calendar option after reload");
    }
    await page.getByRole("button", { name: "AI 모델", exact: true }).click();
    await page.getByRole("region", { name: "등록된 AI 모델", exact: true }).getByText("text-embedding-3-large", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "연결 계정", exact: true }).click();
    await page.getByText("smtp.20b.example.com:587", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("pilot.sender@20b.example.com", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    await page.getByText("저장된 secret 유지", { exact: true }).first().waitFor({ state: "visible", timeout: 10_000 });
    await page.getByRole("button", { name: "개발자", exact: true }).click();
    await page.getByRole("button", { name: "등록 토큰 회전", exact: true }).click();
    await page.getByText("등록 토큰이 생성되었습니다.", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
    return [
      evidence("settings:switch-ai-model-tab"),
      evidence("settings:save-embedding-model"),
      evidence("settings:verify-embedding-model-save-state"),
      evidence("settings:save-account-config"),
      evidence("settings:verify-account-save-state"),
      evidence("settings:select-calendar-startup-view"),
      evidence("settings:verify-startup-view-persistence"),
      evidence("settings:verify-embedding-model-reload-persistence"),
      evidence("settings:verify-account-reload-persistence"),
      evidence("settings:rotate-connector-token"),
    ];
  }

  return [];
}

async function runAccessibilitySmoke(page, routeSpec) {
  const findings = await page.evaluate(() => {
    function isVisible(element) {
      if (!(element instanceof HTMLElement) && !(element instanceof SVGElement)) return false;
      if (element.closest("[hidden], [aria-hidden='true']")) return false;
      const style = window.getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
      return element.getClientRects().length > 0;
    }

    function textFromIdRefs(value) {
      return value
        .split(/\s+/)
        .map((id) => document.getElementById(id)?.textContent?.trim() || "")
        .filter(Boolean)
        .join(" ")
        .trim();
    }

    function accessibleName(element) {
      const ariaLabel = element.getAttribute("aria-label")?.trim();
      if (ariaLabel) return ariaLabel;
      const labelledBy = element.getAttribute("aria-labelledby");
      if (labelledBy) {
        const label = textFromIdRefs(labelledBy);
        if (label) return label;
      }
      if ("labels" in element && element.labels?.length) {
        const label = Array.from(element.labels)
          .map((item) => item.textContent?.trim() || "")
          .filter(Boolean)
          .join(" ")
          .trim();
        if (label) return label;
      }
      const title = element.getAttribute("title")?.trim();
      if (title) return title;
      const text = element.textContent?.replace(/\s+/g, " ").trim();
      if (text) return text;
      return "";
    }

    const visibleIds = new Map();
    for (const element of Array.from(document.querySelectorAll("[id]"))) {
      if (!isVisible(element)) continue;
      const id = element.getAttribute("id");
      if (!id) continue;
      visibleIds.set(id, (visibleIds.get(id) || 0) + 1);
    }
    const duplicateIds = Array.from(visibleIds.entries())
      .filter(([, count]) => count > 1)
      .map(([id, count]) => `${id}(${count})`);

    const selector = [
      "button",
      "a[href]",
      "input",
      "select",
      "textarea",
      "[role='button']",
      "[role='link']",
      "[role='tab']",
      "[role='searchbox']",
      "[role='menuitem']",
    ].join(",");
    const unnamedInteractive = Array.from(document.querySelectorAll(selector))
      .filter((element) => isVisible(element))
      .filter((element) => !element.hasAttribute("disabled"))
      .filter((element) => element.getAttribute("aria-disabled") !== "true")
      .filter((element) => !accessibleName(element))
      .slice(0, 10)
      .map((element) => {
        const tag = element.tagName.toLowerCase();
        const role = element.getAttribute("role");
        const type = element.getAttribute("type");
        return [tag, role ? `role=${role}` : "", type ? `type=${type}` : ""].filter(Boolean).join("[") + (role || type ? "]" : "");
      });

    return { duplicateIds, unnamedInteractive };
  });

  if (findings.duplicateIds.length > 0) {
    throw new Error(`Route ${routeSpec.path} has visible duplicate IDs: ${findings.duplicateIds.join(", ")}`);
  }
  if (findings.unnamedInteractive.length > 0) {
    throw new Error(`Route ${routeSpec.path} has visible interactive controls without accessible names: ${findings.unnamedInteractive.join(", ")}`);
  }

  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  });
  let focusTarget = null;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await page.keyboard.press("Tab");
    focusTarget = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element) return null;
      return {
        tagName: element.tagName,
        role: element.getAttribute("role"),
        ariaLabel: element.getAttribute("aria-label"),
        text: element.textContent?.replace(/\s+/g, " ").trim().slice(0, 80) || "",
      };
    });
    if (focusTarget && focusTarget.tagName !== "BODY" && focusTarget.tagName !== "HTML") break;
  }
  if (!focusTarget || focusTarget.tagName === "BODY" || focusTarget.tagName === "HTML") {
    throw new Error(`Route ${routeSpec.path} did not expose a keyboard focus target after pressing Tab`);
  }

  return [`${routeSpec.name}:a11y-basics`];
}

async function runRouteSmoke(context, routeSpec, viewportSpec, viewportCount, screenshotDir) {
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
  await installRoutes(page);
  await page.goto(new URL(routeSpec.path, baseUrl).href, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
  await page.locator("body").waitFor({ state: "visible", timeout: 20_000 });
  const bodyText = await page.locator("body").innerText({ timeout: 10_000 });
  const expectedTexts = Array.isArray(routeSpec.expectedText) ? routeSpec.expectedText : [routeSpec.expectedText];
  if (!expectedTexts.some((expectedText) => bodyText.includes(expectedText))) {
    const bodySnippet = bodyText.replace(/\s+/g, " ").trim().slice(0, 500);
    throw new Error(
      `Route ${routeSpec.path} did not render expected text: ${expectedTexts.join(" or ")}. Body snippet: ${bodySnippet}`,
    );
  }
  if (bodyText.includes("404") || bodyText.includes("This page could not be found")) {
    throw new Error(`Route ${routeSpec.path} rendered a not-found page`);
  }
  if (consoleErrors.length > 0) {
    throw new Error(`Route ${routeSpec.path} emitted console errors:\n${consoleErrors.join("\n")}`);
  }
  const interactionEvidence = await runCriticalInteractionSmoke(page, routeSpec, viewportSpec);
  const accessibilityEvidence = await runAccessibilitySmoke(page, routeSpec);
  const screenshotPath = resolveFullProductArtifactPath(
    screenshotDir,
    fullProductScreenshotName(routeSpec, viewportSpec, viewportCount),
  );
  const screenshotArtifact = await captureSmokeScreenshot(
    page,
    screenshotPath,
    `${viewportSpec.name}:${routeSpec.path}`,
  );
  await page.close();
  return { screenshotPath: screenshotArtifact, interactionEvidence, accessibilityEvidence };
}

async function main() {
  let serverProcess = null;
  let browser = null;
  try {
    const screenshotDir = await createFullProductArtifactDirectory(requestedScreenshotProfile);
    serverProcess = await startServerIfNeeded();
    browser = await launchBrowser();
    const screenshots = [];
    const interactions = [];
    const accessibility = [];
    const viewportSpecs = resolveFullProductViewportSpecs(process.env.NARUON_FULL_PRODUCT_VIEWPORTS || "desktop");
    for (const viewportSpec of viewportSpecs) {
      const context = await browser.newContext({
        viewport: { width: viewportSpec.width, height: viewportSpec.height },
        isMobile: Boolean(viewportSpec.isMobile),
      });
      for (const routeSpec of FULL_PRODUCT_ROUTES) {
        const result = await runRouteSmoke(context, routeSpec, viewportSpec, viewportSpecs.length, screenshotDir);
        screenshots.push(result.screenshotPath);
        interactions.push(...result.interactionEvidence);
        accessibility.push(...result.accessibilityEvidence);
      }
      await context.close();
    }
    log("Naruon full-product route smoke passed.");
    log(`Routes: ${FULL_PRODUCT_ROUTES.map((route) => route.path).join(", ")}`);
    log(`Viewports: ${viewportSpecs.map((viewport) => `${viewport.name}(${viewport.width}x${viewport.height})`).join(", ")}`);
    if (interactions.length > 0) {
      log(`Critical interactions: ${interactions.join(", ")}`);
    }
    log(`Accessibility checks: ${accessibility.join(", ")}`);
    log(`Screenshots: ${screenshots.join(", ")}`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (serverProcess) await stopServerProcess(serverProcess);
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
