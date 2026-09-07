/* @vitest-environment jsdom */
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';

interface RepositoryProps {
  isDocumentActionLoading: boolean;
  activeDocumentAction: string | null;
  documentActionStatus: string;
  requestDocumentUpload: () => Promise<void>;
  requestDocumentAction: (
    action: 'reparse' | 'embedding-regeneration-intent' | 'webdav-materialization-intent',
  ) => Promise<void>;
}

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  postForm: vi.fn(),
}));
const repositoryProps = vi.hoisted(() => ({
  current: null as RepositoryProps | null,
}));

vi.mock('@/lib/api-client', () => ({ apiClient: apiClientMock }));
vi.mock('lucide-react', () => ({
  Database: () => <svg aria-hidden="true" />,
}));
vi.mock('./data-layout/DocumentRepositoryTab', () => ({
  DocumentRepositoryTab: (props: RepositoryProps) => {
    repositoryProps.current = props;
    return null;
  },
}));
vi.mock('./data-layout/IngestionPipelineTab', () => ({ IngestionPipelineTab: () => null }));
vi.mock('./data-layout/EmbeddingTab', () => ({ EmbeddingTab: () => null }));
vi.mock('./data-layout/QualityCheckTab', () => ({ QualityCheckTab: () => null }));

import { DataLayout } from './DataLayout';

const workspaceDocument = {
  asset_key: 'workspace-document-1',
  asset_type: 'workspace_document',
  display_name: '운영 계약.md',
  source_label: '로컬 문서',
  state_code: 'ready',
  detail_text: '검토 가능한 문서 근거',
  content_chars: 128,
  captured_at: '2026-09-07T00:00:00Z',
  evidence_source: 'workspace_document',
  thread_key: 'thread-1',
  provider_write_executed: false,
};

const qualitySurface = {
  repositories: [],
  pipeline_stages: [],
  connector_events: [],
  repository_assets: [workspaceDocument],
  provider_write_executed: false,
};

const evidenceSnapshot = {
  snapshot_version: 'data_quality_evidence_snapshot.v1',
  privacy_redaction_policy: { raw_content_exposed: false },
};

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('DataLayout document action lifecycle', () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    root = null;
    container?.remove();
    container = null;
    repositoryProps.current = null;
    vi.clearAllMocks();
  });

  it('keeps the shared action lock until the post-action quality refresh settles', async () => {
    let qualityRequestCount = 0;
    let resolveRefresh: ((value: typeof qualitySurface) => void) | undefined;
    const pendingRefresh = new Promise<typeof qualitySurface>((resolve) => {
      resolveRefresh = resolve;
    });

    apiClientMock.get.mockImplementation((path: string) => {
      if (path === '/api/webdav/accounts') return Promise.resolve([]);
      if (path === '/api/webdav/folders') return Promise.resolve([]);
      if (path === '/api/data/quality-surface/evidence-snapshot') return Promise.resolve(evidenceSnapshot);
      if (path === '/api/data/quality-surface') {
        qualityRequestCount += 1;
        return qualityRequestCount === 1 ? Promise.resolve(qualitySurface) : pendingRefresh;
      }
      return Promise.reject(new Error(`Unexpected GET path: ${path}`));
    });
    apiClientMock.post.mockResolvedValue({
      document_name: workspaceDocument.display_name,
      message: '재파싱 완료',
      provider_write_executed: false,
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<DataLayout />);
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    });
    await flushAsyncWork();
    await flushAsyncWork();

    expect(repositoryProps.current).not.toBeNull();
    expect(repositoryProps.current?.isDocumentActionLoading).toBe(false);

    let firstRequest: Promise<void> | undefined;
    await act(async () => {
      firstRequest = repositoryProps.current?.requestDocumentAction('reparse');
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(apiClientMock.post).toHaveBeenCalledTimes(1);
    expect(repositoryProps.current?.isDocumentActionLoading).toBe(true);
    expect(repositoryProps.current?.activeDocumentAction).toBe('reparse');
    expect(repositoryProps.current?.documentActionStatus).toBe('loading');

    await act(async () => {
      void repositoryProps.current?.requestDocumentAction('embedding-regeneration-intent');
      await Promise.resolve();
    });
    expect(apiClientMock.post).toHaveBeenCalledTimes(1);
    expect(repositoryProps.current?.activeDocumentAction).toBe('reparse');
    expect(repositoryProps.current?.documentActionStatus).toBe('loading');

    // A rejected re-entry must not overwrite the active action's status while
    // validating prerequisites for an action that cannot start.
    await act(async () => {
      void repositoryProps.current?.requestDocumentAction('webdav-materialization-intent');
      await Promise.resolve();
    });
    expect(apiClientMock.post).toHaveBeenCalledTimes(1);
    expect(repositoryProps.current?.activeDocumentAction).toBe('reparse');
    expect(repositoryProps.current?.documentActionStatus).toBe('loading');

    // Upload shares the same lock; even a programmatic call without a selected
    // file must leave the active operation's status untouched.
    await act(async () => {
      void repositoryProps.current?.requestDocumentUpload();
      await Promise.resolve();
    });
    expect(apiClientMock.post).toHaveBeenCalledTimes(1);
    expect(repositoryProps.current?.activeDocumentAction).toBe('reparse');
    expect(repositoryProps.current?.documentActionStatus).toBe('loading');

    await act(async () => {
      resolveRefresh?.(qualitySurface);
      await pendingRefresh;
      await firstRequest;
    });

    expect(repositoryProps.current?.isDocumentActionLoading).toBe(false);
    expect(repositoryProps.current?.activeDocumentAction).toBeNull();
    expect(repositoryProps.current?.documentActionStatus).toBe('success');
  });
});