/* @vitest-environment jsdom */
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./data-layout/IngestionPipelineTab', () => ({ IngestionPipelineTab: () => null }));
vi.mock('./data-layout/EmbeddingTab', () => ({ EmbeddingTab: () => null }));
vi.mock('./data-layout/QualityCheckTab', () => ({ QualityCheckTab: () => null }));

import { DataLayout } from './DataLayout';

const documentAsset = {
  asset_key: 'document-lifecycle', asset_type: 'workspace_document',
  display_name: 'review-note.md', source_label: '문서', state_code: 'ready',
  detail_text: '문서 검토', content_chars: 12, captured_at: '2026-09-01T00:00:00Z',
  evidence_source: 'workspace_document', thread_key: null, provider_write_executed: false,
};
const qualitySurface = {
  repositories: [], pipeline_stages: [], connector_events: [],
  repository_assets: [documentAsset], provider_write_executed: false,
};
const storedDocument = {
  document_id: documentAsset.asset_key, workspace_id: 'workspace-test',
  document_name: documentAsset.display_name, document_type: 'text/markdown',
  document_status: 'parsed', content_chars: 12, provider_write_executed: false,
  provenance: 'server-authoritative', audit_event: 'data.document.reparsed',
  message: '문서 작업 완료',
};

function jsonResponse(responseBody: unknown, responseStatus = 200) {
  return {
    ok: responseStatus >= 200 && responseStatus < 300,
    status: responseStatus,
    statusText: responseStatus < 400 ? 'OK' : 'Service Unavailable',
    json: async () => responseBody,
  } as Response;
}

async function flushState() {
  await act(async () => { await vi.runOnlyPendingTimersAsync(); });
}

describe('DataLayout document request lifecycle', () => {
  let reactRoot: Root | null = null;
  let testContainer: HTMLDivElement | null = null;
  const pendingResponses: Array<ReturnType<typeof Promise.withResolvers<Response>>> = [];

  beforeEach(() => { vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }); });

  afterEach(async () => {
    await act(async () => {
      pendingResponses.splice(0).forEach((pendingResponse) => pendingResponse.resolve(jsonResponse(qualitySurface)));
      await Promise.resolve();
    });
    if (reactRoot) act(() => reactRoot?.unmount());
    reactRoot = null;
    testContainer?.remove();
    testContainer = null;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  function deferredResponse() {
    const pendingResponse = Promise.withResolvers<Response>();
    pendingResponses.push(pendingResponse);
    return pendingResponse;
  }

  async function mountWorkspace(postResponse: Promise<Response>, refreshResponse: Promise<Response> | (() => Promise<Response>), initialResponse?: Promise<Response>) {
    let surfaceReads = 0;
    const fetchMock = vi.fn(async (requestInput: RequestInfo | URL, requestInit?: RequestInit) => {
      const requestPath = String(requestInput);
      if (requestInit?.method === 'POST') return postResponse;
      if (requestPath === '/api/data/quality-surface') {
        if (++surfaceReads === 1) return initialResponse ?? jsonResponse(qualitySurface);
        return typeof refreshResponse === 'function' ? refreshResponse() : refreshResponse;
      }
      if (requestPath === '/api/data/quality-surface/evidence-snapshot') return jsonResponse({
        snapshot_version: 'data_quality_evidence_snapshot.v1', privacy_redaction_policy: { raw_content_exposed: false },
      });
      if (requestPath === '/api/webdav/accounts' || requestPath === '/api/webdav/folders') return jsonResponse([]);
      throw new Error(`Unexpected unit request: ${requestPath}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    testContainer = document.createElement('div');
    document.body.appendChild(testContainer);
    reactRoot = createRoot(testContainer);
    await act(async () => { reactRoot?.render(<DataLayout />); });
    await flushState();
    if (!initialResponse) expect(actionButton('reparse').disabled).toBe(false);
    return fetchMock;
  }

  function actionButton(actionName: string) {
    const buttonElement = testContainer?.querySelector<HTMLButtonElement>(`[data-document-action="${actionName}"]`);
    expect(buttonElement).not.toBeNull();
    return buttonElement!;
  }

  async function selectDocument(fileName: string) {
    const fileInput = testContainer!.querySelector<HTMLInputElement>('input[accept*=".markdown"]')!;
    const sourceFile = new File(['review text'], fileName, { type: 'text/markdown' });
    Object.defineProperty(sourceFile, 'text', { value: async () => 'review text' });
    Object.defineProperty(fileInput, 'files', { configurable: true, value: [sourceFile] });
    await act(async () => { fileInput.dispatchEvent(new Event('change', { bubbles: true })); });
    return fileInput;
  }

  it.each(['upload', 'reparse'])('keeps %s locked until the post-write refresh completes', async (actionName) => {
    const postResponse = deferredResponse();
    const refreshResponse = deferredResponse();
    await mountWorkspace(postResponse.promise, refreshResponse.promise);
    if (actionName === 'upload') await selectDocument('review-note.md');
    await act(async () => { actionButton(actionName).click(); });
    await act(async () => { postResponse.resolve(jsonResponse(storedDocument)); });
    await flushState();
    expect(actionButton(actionName).getAttribute('aria-busy')).toBe('true');
    expect(actionButton(actionName).disabled).toBe(true);
    expect(actionButton('embedding-regeneration-intent').disabled).toBe(true);
    await act(async () => { refreshResponse.resolve(jsonResponse(qualitySurface)); });
    await flushState();
    expect(actionButton(actionName).getAttribute('aria-busy')).toBe('false');
    expect(actionButton(actionName).disabled).toBe(false);
  });

  it('does not send two writes when the same action is invoked before React commits', async () => {
    const postResponse = deferredResponse();
    const fetchMock = await mountWorkspace(postResponse.promise, Promise.resolve(jsonResponse(qualitySurface)));
    await act(async () => {
      actionButton('reparse').click();
      actionButton('reparse').click();
    });
    expect(fetchMock.mock.calls.filter(([, requestInit]) => requestInit?.method === 'POST')).toHaveLength(1);
    expect(actionButton('reparse').getAttribute('aria-busy')).toBe('true');
  });

  it('keeps an upload locked when the file selection changes during its write', async () => {
    const postResponse = deferredResponse();
    const fetchMock = await mountWorkspace(postResponse.promise, Promise.resolve(jsonResponse(qualitySurface)));
    await selectDocument('first-note.md');
    await act(async () => { actionButton('upload').click(); });
    await selectDocument('second-note.md');
    expect(actionButton('upload').disabled).toBe(true);
    expect(actionButton('upload').getAttribute('aria-busy')).toBe('true');
    await act(async () => { actionButton('upload').click(); });
    expect(fetchMock.mock.calls.filter(([, requestInit]) => requestInit?.method === 'POST')).toHaveLength(1);
  });

  it('distinguishes a committed write from a failed refresh and retries only reads', async () => {
    const refreshResponse = deferredResponse();
    let refreshAttempts = 0;
    const fetchMock = await mountWorkspace(Promise.resolve(jsonResponse(storedDocument)), () => ++refreshAttempts === 1 ? refreshResponse.promise : Promise.resolve(jsonResponse(qualitySurface)));
    const errorLog = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    await act(async () => { actionButton('reparse').click(); });
    await act(async () => { refreshResponse.resolve(jsonResponse({ message: 'unavailable' }, 503)); });
    await flushState();
    expect(errorLog.mock.calls).toEqual([['Data quality surface fetch error', { status: 503, error_name: 'ApiClientError' }]]);
    expect(testContainer!.textContent).toContain('요청 결과를 받았지만 목록을 새로 불러오지 못했습니다.');
    expect(testContainer!.textContent).not.toContain('문서 작업에 실패했습니다.');
    const retryButton = Array.from(testContainer!.querySelectorAll('button')).find((buttonElement) => buttonElement.textContent === '목록 다시 불러오기');
    expect(retryButton).toBeDefined();
    await act(async () => { retryButton?.click(); });
    await flushState();
    expect(fetchMock.mock.calls.filter(([, requestInit]) => requestInit?.method === 'POST')).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([requestInput]) => String(requestInput) === '/api/data/quality-surface')).toHaveLength(3);
    expect(testContainer!.textContent).not.toContain('요청 결과를 받았지만 목록을 새로 불러오지 못했습니다.');
    expect(actionButton('reparse').disabled).toBe(false);
    expect(errorLog).toHaveBeenCalledTimes(1);
  });

  it('ignores an initial response arriving after the post-write refresh', async () => {
    const initialResponse = deferredResponse();
    const freshSurface = { ...qualitySurface, repository_assets: [{ ...documentAsset, display_name: 'fresh-after-write.md' }] };
    await mountWorkspace(Promise.resolve(jsonResponse(storedDocument)), Promise.resolve(jsonResponse(freshSurface)), initialResponse.promise);
    await selectDocument('review-note.md');
    await act(async () => { actionButton('upload').click(); });
    await flushState();
    expect(testContainer!.textContent).toContain('fresh-after-write.md');
    await act(async () => { initialResponse.resolve(jsonResponse({ ...qualitySurface, repository_assets: [{ ...documentAsset, display_name: 'obsolete-before-write.md' }] })); });
    await flushState();
    expect(testContainer!.textContent).toContain('fresh-after-write.md');
    expect(testContainer!.textContent).not.toContain('obsolete-before-write.md');
  });

  it('does not start a refresh for a write response received after unmount', async () => {
    const postResponse = deferredResponse();
    const fetchMock = await mountWorkspace(postResponse.promise, Promise.resolve(jsonResponse(qualitySurface)));
    await act(async () => { actionButton('reparse').click(); });
    act(() => reactRoot?.unmount());
    reactRoot = null;
    await act(async () => { postResponse.resolve(jsonResponse(storedDocument)); });
    await flushState();
    expect(fetchMock.mock.calls.filter(([, requestInit]) => requestInit?.method === 'POST')).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([requestInput]) => String(requestInput) === '/api/data/quality-surface')).toHaveLength(1);
  });
});
