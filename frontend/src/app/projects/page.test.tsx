/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a>,
}));

vi.mock("lucide-react", () => ({
  CalendarDays: () => <svg aria-hidden="true" />,
  CheckCircle2: () => <svg aria-hidden="true" />,
  Clock: () => <svg aria-hidden="true" />,
  FileText: () => <svg aria-hidden="true" />,
  FolderOpen: () => <svg aria-hidden="true" />,
  GitBranch: () => <svg aria-hidden="true" />,
  ListChecks: () => <svg aria-hidden="true" />,
  Network: () => <svg aria-hidden="true" />,
  Search: () => <svg aria-hidden="true" />,
  User: () => <svg aria-hidden="true" />,
}));

import ProjectsPage from "./page";

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 500) {
  return Promise.resolve({
    ok,
    status,
    statusText: ok ? "OK" : "Server Error",
    json: () => Promise.resolve(body),
  } as Response);
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function setNativeValue(element: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, value: string) {
  const prototype = Object.getPrototypeOf(element);
  const prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  prototypeValueSetter?.call(element, value);
}

describe("ProjectsPage", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    root = null;
    container?.remove();
    container = null;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("loads project folders and ticket tasks through signed APIs", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.get("Authorization")).toBeNull();
      expect(headers.get("X-User-Id")).toBeNull();
      expect(headers.get("X-Organization-Id")).toBeNull();

      const path = String(input);
      if (path === "/auth/session") {
        return jsonResponse({
          authenticated: true,
          claims: {
            userId: "alice",
            organizationId: "org-acme",
            workspaceId: "workspace-org-acme",
          },
        });
      }
      if (path === "/api/webdav/folders") {
        return jsonResponse([
          {
            folder_uid: "webdav_folder_roadmap",
            project_name: "Naruon Roadmap 2026",
            webdav_path: "/Projects/Naruon_Roadmap_2026",
            owner_user_id: "alice",
            organization_id: "org-acme",
          },
          {
            folder_uid: "webdav_folder_second",
            project_name: "Second Project",
            webdav_path: "/Projects/Second_Project",
            owner_user_id: "alice",
            organization_id: "org-acme",
          },
          {
            folder_uid: "webdav_folder_rival",
            project_name: "Rival Project",
            webdav_path: "/Projects/Rival_Project",
            owner_user_id: "mallory",
            organization_id: "org-rival",
          },
        ]);
      }
      if (path === "/api/tasks") {
        return jsonResponse([
          {
            id: "task-q2-owner",
            title: "리소스 배정 검토 회의",
            status: "blocked",
            priority: "urgent",
            source_type: "email",
            source_email_id: "<q2@example.com>",
            related_thread_id: "thread-q2",
            created_at: "2026-05-19T00:00:00Z",
            updated_at: "2026-05-21T00:00:00Z",
          },
          {
            id: "task-webdav-evidence",
            title: "첨부파일 WebDAV 폴더 정리",
            status: "done",
            priority: "low",
            source_type: "webdav",
            source_email_id: "<q2@example.com>",
            related_thread_id: "thread-q2",
            created_at: "2026-05-19T00:00:00Z",
            updated_at: "2026-05-24T00:00:00Z",
          },
        ]);
      }
      if (path === "/api/projects/candidates") {
        return jsonResponse({ candidates: [] });
      }
      return jsonResponse({}, false, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<ProjectsPage />);
    });
    await flushAsyncWork();

    expect(fetchMock).toHaveBeenCalledWith("/api/webdav/folders", expect.objectContaining({ headers: expect.any(Object) }));
    expect(fetchMock).toHaveBeenCalledWith("/api/tasks", expect.objectContaining({ headers: expect.any(Object) }));
    expect(container.textContent).toContain("Naruon Roadmap 2026");
    expect(container.textContent).not.toContain("Rival Project");
    expect(container.textContent).not.toContain("webdav_folder_roadmap");
    expect(container.textContent).not.toContain("/Projects/Naruon_Roadmap_2026");
    expect(container.textContent).toContain("외부 저장소 쓰기는 별도 승인 전까지 실행하지 않습니다");
    expect(container.textContent).toContain("WebDAV 폴더 근거");
    expect(container.textContent).toContain("진행률 확인 불가");
    expect(container.textContent).not.toContain("50%");
    expect(container.querySelectorAll('progress')).toHaveLength(0);
    const secondProjectButton = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes('Second Project') && button.textContent?.includes('WebDAV 프로젝트'));
    expect(secondProjectButton?.textContent).toContain("진행률 확인 불가");
    expect(secondProjectButton?.textContent).toContain("상태 확인 불가");
    expect(container.querySelector('[aria-label="프로젝트 개요"]')?.textContent).toContain("상태 확인 불가");
    expect(container.textContent).toContain("리소스 배정 검토 회의");
    expect(container.textContent).toContain("스레드 근거 연결됨");
    expect(container.textContent).not.toContain("thread-q2");
    expect(container.textContent).not.toContain("<q2@example.com>");
    expect(container.textContent).toContain("프로젝트 액션");
    expect(container.textContent).toContain("새 프로젝트");
    expect(container.textContent).toContain("작업 보드 열기");
    expect(container.textContent).toContain("의사결정 추가");
    expect(container.textContent).toContain("관련 문서/메일 연결");
    expect(container.textContent).not.toContain("Naruon 2.0 런칭");

    const evidenceNote = container.querySelector<HTMLTextAreaElement>('#project-evidence-note');
    const evidenceSource = container.querySelector<HTMLSelectElement>('#project-evidence-source');
    const saveButton = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes("근거 저장"));
    expect(evidenceNote).not.toBeNull();
    expect(evidenceSource).not.toBeNull();
    expect(saveButton).toBeDefined();
    expect(saveButton?.disabled).toBe(true);
    expect(container.textContent).toContain("메모 저장은 아직 지원하지 않습니다. 입력 내용은 이 화면에서만 유지되며 새로고침하면 사라집니다.");

    await act(async () => {
      setNativeValue(evidenceNote!, "이사회 승인 근거와 WebDAV 경계를 함께 검토합니다.");
      evidenceNote!.dispatchEvent(new Event("input", { bubbles: true }));
      setNativeValue(evidenceSource!, "document");
      evidenceSource!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.textContent).toContain("문서 저장소 승인 기록 기준");

    await act(async () => {
      saveButton!.click();
    });
    expect(container.textContent).not.toContain("프로젝트 근거가 저장되었습니다");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    expect(container.textContent).toContain("이사회 승인 근거와 WebDAV 경계를 함께 검토합니다.");
  });

  it("renders the semantic project graph command center with paragraph citations", async () => {
    const citation = {
      content_segment_uid: "segment-alpha-1",
      source_kind: "email_body",
      source_record_uid: "<alpha@example.com>",
      heading_path: "Project kickoff",
      segment_path: "/document[1]/paragraph[1]",
      ordinal_index: 1,
      safe_text_excerpt: "결제 화면은 카드 승인 실패 시 재시도 안내를 반드시 보여줘야 합니다.",
    };
    const candidate = {
      candidate_uid: "project_candidate:alpha",
      project_uid: "project_candidate:alpha",
      title: "Project: Alpha Checkout",
      status_code: "needs_review",
      score: 0.87,
      object_count: 10,
      requirement_count: 1,
      issue_count: 1,
      milestone_count: 1,
      deliverable_count: 1,
      participant_count: 1,
      source_segment_count: 1,
      representative_object_uids: ["requirement:alpha-payment-retry"],
      citation_bundle: [citation],
      updated_at: "2026-07-02T00:00:00Z",
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/auth/session") {
        return jsonResponse({
          authenticated: true,
          claims: {
            userId: "alice",
            organizationId: "org-acme",
            workspaceId: "workspace-org-acme",
          },
        });
      }
      if (path === "/api/webdav/folders") return jsonResponse([]);
      if (path === "/api/tasks") return jsonResponse([]);
      if (path === "/api/projects/candidates") {
        return jsonResponse({ candidates: [candidate] });
      }
      if (path === "/api/projects/project_candidate%3Aalpha/traceability") {
        return jsonResponse({
          project_uid: "project_candidate:alpha",
          candidate,
          objects: [
            {
              object_uid: "requirement:alpha-payment-retry",
              object_type: "requirement",
              title: "카드 승인 실패 재시도 안내",
              summary: "결제 화면은 승인 실패 사용자가 다시 시도할 수 있는 안내를 제공해야 합니다.",
              status_code: "needs_review",
              confidence: 0.92,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "issue:alpha-pg-timeout",
              object_type: "issue",
              title: "PG timeout risk",
              summary: "PG 응답 지연 시 결제 재시도 UX가 필요합니다.",
              status_code: "open",
              confidence: 0.81,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "milestone:alpha-beta-freeze",
              object_type: "milestone",
              title: "7월 결제 UX 베타 동결",
              summary: "결제 재시도 안내는 베타 동결 전에 검증되어야 합니다.",
              status_code: "open",
              confidence: 0.84,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "wbs:alpha-retry-work-package",
              object_type: "wbs_item",
              title: "결제 재시도 UX 작업 패키지",
              summary: "프론트엔드 상태, PG timeout 처리, QA 검증을 하나의 WBS 항목으로 묶습니다.",
              status_code: "open",
              confidence: 0.8,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "deliverable:alpha-qa-report",
              object_type: "deliverable",
              title: "결제 재시도 QA 산출물",
              summary: "카드 승인 실패 재시도 안내의 검증 결과가 산출물로 관리됩니다.",
              status_code: "open",
              confidence: 0.79,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "report:alpha-weekly",
              object_type: "report_delta",
              title: "주간 보고: 결제 재시도 리스크",
              summary: "승인 실패 UX와 PG timeout 리스크가 이번 주 보고 항목입니다.",
              status_code: "open",
              confidence: 0.78,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "wiki:alpha-checkout",
              object_type: "wiki_projection",
              title: "Alpha Checkout 위키 초안",
              summary: "결제 재시도 요구사항과 근거 문단을 위키 페이지로 투영합니다.",
              status_code: "open",
              confidence: 0.76,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "data:alpha-failure-reason",
              object_type: "data_requirement",
              title: "결제 실패 사유 데이터 요건",
              summary: "승인 실패와 재시도 안내를 연결할 실패 사유 필드가 필요합니다.",
              status_code: "open",
              confidence: 0.75,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "erd:alpha-payment-attempt",
              object_type: "erd_candidate",
              title: "PaymentAttempt ERD 후보",
              summary: "결제 시도, 승인 실패, 재시도 안내 상태를 ERD 후보로 관리합니다.",
              status_code: "open",
              confidence: 0.74,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
            {
              object_uid: "infra:alpha-pg-timeout-observability",
              object_type: "infra_requirement",
              title: "PG timeout 관측 인프라",
              summary: "PG 응답 지연을 감지해 재시도 UX 품질을 추적합니다.",
              status_code: "open",
              confidence: 0.73,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
              attributes: {},
            },
          ],
          edges: [
            {
              edge_uid: "edge:segment-alpha-1:requirement:alpha-payment-retry",
              source_uid: "segment-alpha-1",
              target_uid: "requirement:alpha-payment-retry",
              edge_type: "evidences",
              confidence: 0.92,
              source_segment_uids: ["segment-alpha-1"],
              citation_bundle: [citation],
            },
          ],
        });
      }
      if (path === "/api/projects/project_candidate%3Aalpha/evidence/requirement%3Aalpha-payment-retry") {
        return jsonResponse({
          project_uid: "project_candidate:alpha",
          object_uid: "requirement:alpha-payment-retry",
          object_type: "requirement",
          title: "카드 승인 실패 재시도 안내",
          summary: "결제 화면은 승인 실패 사용자가 다시 시도할 수 있는 안내를 제공해야 합니다.",
          status_code: "needs_review",
          confidence: 0.93,
          citation_bundle: [citation],
        });
      }
      if (path === "/api/projects/project_candidate%3Aalpha/corrections") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        expect(init?.method).toBe("POST");
        expect(body).toMatchObject({
          object_uid: "requirement:alpha-payment-retry",
          correction_action: "mark_evidence_reviewed",
          source_segment_uids: ["segment-alpha-1"],
        });
        return jsonResponse({
          correction_uid: "correction-alpha-1",
          object_uid: "requirement:alpha-payment-retry",
          correction_action: "mark_evidence_reviewed",
          before_json: { status_code: "needs_review" },
          after_json: { status_code: "approved", title: "카드 승인 실패 재시도 안내" },
          rationale: "Reviewed from the Project Command Center Evidence Inspector.",
          actor_user_id: "alice",
          source_segment_uids: ["segment-alpha-1"],
          created_at: "2026-07-03T00:00:00Z",
        });
      }
      if (path === "/api/projects/candidates/project_candidate%3Aalpha/confirm") {
        expect(init?.method).toBe("POST");
        return jsonResponse({ ...candidate, status_code: "confirmed" });
      }
      return jsonResponse({}, false, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<ProjectsPage />);
    });
    await flushAsyncWork();
    await flushAsyncWork();
    await flushAsyncWork();

    expect(fetchMock).toHaveBeenCalledWith("/api/projects/candidates", expect.objectContaining({ headers: expect.any(Object) }));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project_candidate%3Aalpha/traceability", expect.objectContaining({ headers: expect.any(Object) }));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project_candidate%3Aalpha/evidence/requirement%3Aalpha-payment-retry", expect.objectContaining({ headers: expect.any(Object) }));
    expect(container.textContent).toContain("Project: Alpha Checkout");
    expect(container.textContent).toContain("진행률 확인 불가");
    expect(container.textContent).not.toContain("87%");
    expect(container.querySelectorAll('progress')).toHaveLength(0);
    expect(container.textContent).toContain("프로젝트 관계 맥락");
    expect(container.textContent).toContain("Traceability Map");
    expect(container.textContent).toContain("Evidence Inspector");
    expect(container.textContent).toContain("문단 citation 경계 확인됨");
    expect(container.textContent).toContain("문단 KG 근거");
    expect(container.textContent).toContain("카드 승인 실패 재시도 안내");
    expect(container.textContent).toContain("결제 화면은 카드 승인 실패");
    expect(container.textContent).toContain("1 citations");
    expect(container.textContent).toContain("Full evidence 확인됨");
    expect(container.textContent).toContain("Source coverage: 1 문단");
    expect(container.textContent).toContain("자동화 브리프");
    expect(container.textContent).toContain("Automation coverage");
    expect(container.textContent).toContain("5 / 5 domains ready");
    expect(container.textContent).toContain("Buyer KPI: source-backed delivery automation");
    expect(container.textContent).toContain("WBS / 일정");
    expect(container.textContent).toContain("보고 자동 생성");
    expect(container.textContent).toContain("프로젝트 위키");
    expect(container.textContent).toContain("데이터·ERD·인프라");
    expect(container.textContent).toContain("산출물 준비도");
    expect(container.textContent).toContain("주간 보고: 결제 재시도 리스크");
    expect(container.textContent).toContain("Alpha Checkout 위키 초안");
    expect(container.textContent).toContain("PaymentAttempt ERD 후보");
    expect(container.textContent).toContain("보고 초안");
    expect(container.textContent).toContain("Report readiness");
    expect(container.textContent).toContain("Risk action coverage");
    expect(container.textContent).toContain("Status update ready");
    expect(container.textContent).toContain("2 / 2 drafts ready");
    expect(container.textContent).toContain("Reviewer KPI: report-ready status update");
    expect(container.textContent).toContain("주간 보고 초안");
    expect(container.textContent).toContain("일일 보고 초안");
    expect(container.textContent).toContain("상태 자동 업데이트: PG timeout risk 검토 필요");
    expect(container.textContent).toContain("다음 액션: PG timeout risk 확인");
    expect(container.textContent).toContain("검토자 액션: 2개 보고 초안 근거 확인");
    expect(container.textContent).toContain("컨트롤 준비도");
    expect(container.textContent).toContain("Control readiness score");
    expect(container.textContent).toContain("Missing evidence count");
    expect(container.textContent).toContain("Acceptance-to-action coverage");
    expect(container.textContent).toContain("Scope-risk balance");
    expect(container.textContent).toContain("5 / 5 controls ready");
    expect(container.textContent).toContain("Diligence KPI: source-backed control readiness");
    expect(container.textContent).toContain("Acceptance coverage");
    expect(container.textContent).toContain("Schedule confidence");
    expect(container.textContent).toContain("Scope clarity");
    expect(container.textContent).toContain("Data/infra readiness");
    expect(container.textContent).toContain("Owner/action readiness");
    expect(container.textContent).toContain("실행 준비 종합: 5개 컨트롤이 문단 근거로 준비됨");
    expect(container.textContent).toContain("검토자 액션: 누락 근거 없음, 인수 검토 가능");

    const reviewButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("문단 근거 검토 저장"));
    expect(reviewButton).toBeDefined();
    await act(async () => {
      reviewButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();
    expect(container.textContent).toContain("Correction trail 저장됨");
    expect(container.textContent).toContain("approved");

    const confirmButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes("프로젝트 후보 확정"));
    expect(confirmButton).toBeDefined();
    await act(async () => {
      confirmButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flushAsyncWork();
    expect(container.textContent).toContain("프로젝트 후보 확정됨");

    expect(container.textContent).not.toContain("segment-alpha-1");
    expect(container.textContent).not.toContain("<alpha@example.com>");
    expect(container.textContent).not.toContain("correction-alpha-1");
  });

  it("does not render empty metrics while project sources are pending", async () => {
    const pendingSources = Promise.withResolvers<void>();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      await pendingSources.promise;
      const requestPath = String(input);
      if (requestPath === "/auth/session") return jsonResponse({ authenticated: true, claims: { userId: "alice", organizationId: "org-acme" } });
      if (requestPath === "/api/projects/candidates") return jsonResponse({ candidates: [] });
      return jsonResponse([]);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => { root?.render(<ProjectsPage />); });
    expect(container.querySelector('[role="status"]')?.textContent).toContain("불러오는 중");
    expect(container.textContent).not.toContain("원본 연결 작업 대기열");
    expect(container.querySelector('[aria-label="조회된 작업 현황"]')).toBeNull();
    await act(async () => { pendingSources.resolve(); });
    await flushAsyncWork();
    expect(container.textContent).toContain("원본 연결 작업 대기열");
    expect(container.querySelector('[aria-label="조회된 작업 현황"]')).not.toBeNull();
  });

  it.each([
    { sourcePath: "/api/webdav/folders", responseBody: {} },
    { sourcePath: "/api/webdav/folders", responseBody: [null] },
    { sourcePath: "/api/tasks", responseBody: {} },
    { sourcePath: "/api/tasks", responseBody: [null] },
    { sourcePath: "/api/tasks", responseBody: [{ id: "task-invalid", title: "Invalid task", status: "unknown", priority: "normal" }] },
    { sourcePath: "/api/projects/candidates", responseBody: {} },
    { sourcePath: "/api/projects/candidates", responseBody: { candidates: [null] } },
    { sourcePath: "/api/projects/candidates", responseBody: { candidates: [{ project_uid: "project-invalid", title: {} }] } },
    { sourcePath: "/auth/session", responseBody: { authenticated: false } },
    { sourcePath: "/auth/session", responseBody: { authenticated: false, claims: { userId: "alice", organizationId: "org-acme" } } },
  ])("rejects malformed successful response from $sourcePath ($responseBody)", async ({ sourcePath, responseBody }) => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const requestPath = String(input);
      if (requestPath === sourcePath) return jsonResponse(responseBody);
      if (requestPath === "/auth/session") return jsonResponse({ authenticated: true, claims: { userId: "alice", organizationId: "org-acme" } });
      if (requestPath === "/api/projects/candidates") return jsonResponse({ candidates: [] });
      return jsonResponse([]);
    }));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => { root?.render(<ProjectsPage />); });
    await flushAsyncWork();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("프로젝트 근거를 불러오지 못했습니다");
    expect(container.querySelector('[aria-label="조회된 작업 현황"]')).toBeNull();
    expect(container.textContent).not.toContain("원본 연결 작업 대기열");
  });

  it.each(["/api/webdav/folders", "/api/tasks", "/api/projects/candidates", "/auth/session"])("keeps %s failure distinct from empty data and retries", async (failedPath) => {
    let sourceUnavailable = true;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const requestPath = String(input);
      if (requestPath === failedPath && sourceUnavailable) return jsonResponse({ detail: "failed" }, false, 500);
      if (requestPath === "/auth/session") return jsonResponse({ authenticated: true, claims: { userId: "alice", organizationId: "org-acme" } });
      if (requestPath === "/api/projects/candidates") return jsonResponse({ candidates: [] });
      if (requestPath === "/api/webdav/folders" || requestPath === "/api/tasks") return jsonResponse([]);
      return jsonResponse({}, false, 404);
    }));

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<ProjectsPage />);
    });
    await flushAsyncWork();

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("프로젝트 근거를 불러오지 못했습니다");
    expect(
      Array.from(container.querySelectorAll('a[href="/data"]')).some((link) => link.textContent?.includes("원본 연결") || link.textContent?.includes("새 프로젝트")),
    ).toBe(true);
    expect(container.textContent).not.toContain("원본 연결 작업 대기열");
    expect(container.querySelector('[aria-label="조회된 작업 현황"]')).toBeNull();
    expect(container.textContent).not.toContain("서명된 개인 워크스페이스");
    const retryButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "다시 불러오기");
    expect(retryButton).toBeDefined();
    sourceUnavailable = false;
    await act(async () => { retryButton?.click(); });
    await flushAsyncWork();
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.textContent).toContain("원본 연결 작업 대기열");
    expect(container.querySelector('[aria-label="조회된 작업 현황"]')).not.toBeNull();
  });

  it.each([
    { taskStatuses: [], expectedProgress: null },
    { taskStatuses: ['open'], expectedProgress: 0 },
    { taskStatuses: ['done', 'open'], expectedProgress: 50 },
    { taskStatuses: ['done'], expectedProgress: 100 },
  ])("uses only the returned task queue denominator: $taskStatuses", async ({ taskStatuses, expectedProgress }) => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const requestPath = String(input);
      if (requestPath === '/auth/session') return jsonResponse({ authenticated: true, claims: { userId: 'alice', organizationId: 'org-acme' } });
      if (requestPath === '/api/webdav/folders') return jsonResponse([]);
      if (requestPath === '/api/projects/candidates') return jsonResponse({ candidates: [] });
      if (requestPath === '/api/tasks') return jsonResponse(taskStatuses.map((taskStatus, taskIndex) => ({
        id: `task-queue-${taskIndex}`, title: '조회된 작업 검토', status: taskStatus,
        priority: 'normal', source_type: 'email', source_email_id: null, related_thread_id: null,
        created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
      })));
      return jsonResponse({}, false, 404);
    }));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => { root?.render(<ProjectsPage />); });
    await flushAsyncWork();
    expect(container.textContent).toContain('원본 연결 작업 대기열');
    const progressElements = container.querySelectorAll<HTMLProgressElement>('progress');
    if (expectedProgress === null) {
      expect(progressElements).toHaveLength(0);
      expect(container.textContent).toContain('진행률 확인 불가');
      expect(container.textContent).not.toContain('0%');
    } else {
      expect(progressElements).toHaveLength(2);
      expect(container.textContent).toContain(`조회된 ${taskStatuses.length}건 중 ${taskStatuses.filter((taskStatus) => taskStatus === 'done').length}건 완료. 프로젝트별 집계가 아닙니다.`);
      for (const progressElement of progressElements) {
        expect(progressElement.value).toBe(expectedProgress);
        expect(progressElement.max).toBe(100);
        expect(progressElement.getAttribute('aria-label')).toBe('조회된 작업 완료율');
      }
    }
  });

  it("renders an actionable empty state when no returned tasks are registered", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/auth/session") {
          return jsonResponse({
            authenticated: true,
            claims: { userId: "alice", organizationId: "org-acme" },
          });
        }
        if (path === "/api/webdav/folders") {
          return jsonResponse([
            {
              folder_uid: "webdav_folder_empty",
              project_name: "Evidence Empty Project",
              webdav_path: "/Projects/Evidence_Empty",
              owner_user_id: "alice",
              organization_id: "org-acme",
            },
          ]);
        }
        if (path === "/api/tasks") return jsonResponse([]);
        if (path === "/api/projects/candidates") return jsonResponse({ candidates: [] });
        return jsonResponse({}, false, 404);
      }),
    );

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<ProjectsPage />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain("Evidence Empty Project");
    expect(container.textContent).toContain("진행률 확인 불가");
    expect(container.textContent).not.toContain("0%");
    expect(container.textContent).toContain("등록된 작업이 아직 없습니다.");
    expect(container.textContent).toContain("프로젝트별 작업 연결은 아직 지원하지 않습니다.");
    expect(container.querySelector('[role="status"]')?.textContent).toContain("등록된 작업");
    expect(Array.from(container.querySelectorAll('a[href="/tasks"]')).some((link) => link.textContent?.includes("작업 보드 열기"))).toBe(true);
    expect(Array.from(container.querySelectorAll('a[href="/search"]')).some((link) => link.textContent?.includes("관련 근거 찾기"))).toBe(true);
  });
});
