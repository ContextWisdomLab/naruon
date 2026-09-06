/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  getServerSessionClaims: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({ apiClient: apiClientMock }));

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

import { ProjectsLayout } from "./ProjectsLayout";

const candidate = {
  candidate_uid: "project_candidate:alpha",
  project_uid: "project_candidate:alpha",
  title: "Project: Alpha Checkout",
  status_code: "needs_review",
  score: 0.87,
  object_count: 1,
  requirement_count: 1,
  issue_count: 0,
  milestone_count: 0,
  deliverable_count: 0,
  participant_count: 0,
  source_segment_count: 1,
  representative_object_uids: [],
  citation_bundle: [],
  updated_at: "2026-08-03T00:00:00Z",
};

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("ProjectsLayout accessibility", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    root = null;
    container?.remove();
    container = null;
    vi.clearAllMocks();
  });

  it.each(["success", "failure"])("separates evidence loading from review saving (%s)", async (outcome) => {
    const traceObject = {
      object_uid: "project_object:requirement",
      object_type: "requirement",
      title: "Review requirement",
      summary: "Source-backed requirement",
      status_code: "needs_review",
      confidence: 0.87,
      source_segment_uids: [],
      citation_bundle: [],
      attributes: {},
    };
    const evidence = { ...traceObject, project_uid: candidate.project_uid };
    const pendingEvidence = Promise.withResolvers<typeof evidence>();
    const pendingSave = Promise.withResolvers<unknown>();
    const projectPath = "/api/projects/project_candidate%3Aalpha";
    apiClientMock.get.mockImplementation((requestPath: string) => {
      if (requestPath === "/api/webdav/folders" || requestPath === "/api/tasks") return Promise.resolve([]);
      if (requestPath === "/api/projects/candidates") return Promise.resolve({ candidates: [candidate] });
      if (requestPath === `${projectPath}/traceability`) {
        return Promise.resolve({ project_uid: candidate.project_uid, candidate, objects: [traceObject], edges: [] });
      }
      if (requestPath === `${projectPath}/evidence/project_object%3Arequirement`) return pendingEvidence.promise;
      return Promise.reject(new Error(`Unexpected GET path: ${requestPath}`));
    });
    apiClientMock.getServerSessionClaims.mockResolvedValue({ userId: "alice", organizationId: "org-acme" });
    apiClientMock.post.mockReturnValue(pendingSave.promise);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => { root?.render(<ProjectsLayout />); });
    await flushAsyncWork();
    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "문단 근거 검토 저장",
    );
    expect(saveButton).toBeDefined();
    expect(saveButton?.disabled).toBe(true);
    expect(saveButton?.getAttribute("aria-busy")).toBe("false");
    saveButton?.click();
    expect(apiClientMock.post).not.toHaveBeenCalled();
    await act(async () => { pendingEvidence.resolve(evidence); await pendingEvidence.promise; });
    expect(saveButton?.disabled).toBe(false);
    expect(saveButton?.getAttribute("aria-busy")).toBe("false");
    await act(async () => { saveButton?.click(); });
    expect(saveButton?.disabled).toBe(true);
    expect(saveButton?.getAttribute("aria-busy")).toBe("true");
    expect(saveButton?.textContent).toBe("검토 저장 중");
    saveButton?.click();
    expect(apiClientMock.post).toHaveBeenCalledTimes(1);
    expect(apiClientMock.post).toHaveBeenCalledWith(`${projectPath}/corrections`, expect.objectContaining({
      object_uid: traceObject.object_uid, correction_action: "mark_evidence_reviewed",
    }));
    await act(async () => {
      if (outcome === "success") {
        pendingSave.resolve({ object_uid: traceObject.object_uid, after_json: { status_code: "approved" }, created_at: candidate.updated_at });
      } else {
        pendingSave.reject(new Error("Save unavailable"));
      }
    });
    expect(saveButton?.disabled).toBe(false);
    expect(saveButton?.getAttribute("aria-busy")).toBe("false");
    expect(saveButton?.textContent).toBe("문단 근거 검토 저장");
    if (outcome === "failure") expect(container.querySelector('[role="alert"]')?.textContent).toContain("저장하지 못했습니다");
  });

  it("announces candidate confirmation as busy while the request is pending", async () => {
    let resolveConfirmation: ((value: typeof candidate) => void) | undefined;
    const pendingConfirmation = new Promise<typeof candidate>((resolve) => {
      resolveConfirmation = resolve;
    });

    apiClientMock.get.mockImplementation((path: string) => {
      if (path === "/api/webdav/folders") return Promise.resolve([]);
      if (path === "/api/tasks") return Promise.resolve([]);
      if (path === "/api/projects/candidates") {
        return Promise.resolve({ candidates: [candidate] });
      }
      if (path === "/api/projects/project_candidate%3Aalpha/traceability") {
        return Promise.resolve({
          project_uid: candidate.project_uid,
          candidate,
          objects: [],
          edges: [],
        });
      }
      return Promise.reject(new Error(`Unexpected GET path: ${path}`));
    });
    apiClientMock.getServerSessionClaims.mockResolvedValue({
      userId: "alice",
      organizationId: "org-acme",
      workspaceId: "workspace-org-acme",
    });
    apiClientMock.post.mockReturnValue(pendingConfirmation);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<ProjectsLayout />);
    });
    await flushAsyncWork();
    await flushAsyncWork();

    const confirmButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("프로젝트 후보 확정"),
    );
    expect(confirmButton).toBeDefined();
    expect(confirmButton?.disabled).toBe(false);
    expect(confirmButton?.getAttribute("aria-busy")).toBe("false");

    await act(async () => {
      confirmButton?.click();
      await Promise.resolve();
    });

    expect(confirmButton?.disabled).toBe(true);
    expect(confirmButton?.getAttribute("aria-busy")).toBe("true");
    expect(confirmButton?.textContent).toContain("확정 저장 중");
    expect(apiClientMock.post).toHaveBeenCalledWith(
      "/api/projects/candidates/project_candidate%3Aalpha/confirm",
      {},
    );

    await act(async () => {
      resolveConfirmation?.({ ...candidate, status_code: "confirmed" });
      await pendingConfirmation;
    });

    expect(confirmButton?.disabled).toBe(true);
    expect(confirmButton?.getAttribute("aria-busy")).toBe("false");
    expect(confirmButton?.textContent).toContain("프로젝트 후보 확정됨");
  });
});
