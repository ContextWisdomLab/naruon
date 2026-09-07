/* @vitest-environment jsdom */
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('lucide-react', () => ({
  HardDrive: () => <svg aria-hidden="true" />,
  Upload: () => <svg aria-hidden="true" />,
  Loader2: () => <svg aria-hidden="true" />,
  FileText: () => <svg aria-hidden="true" />,
  FolderOpen: () => <svg aria-hidden="true" />,
  Database: () => <svg aria-hidden="true" />,
  RefreshCw: () => <svg aria-hidden="true" />,
  CheckCircle2: () => <svg aria-hidden="true" />,
  Server: () => <svg aria-hidden="true" />,
}));

import { DocumentRepositoryTab } from './DocumentRepositoryTab';

const webdavAccount = {
  source_id: 'webdav-customer',
  display_label: 'Customer WebDAV',
  writeback_enabled: true,
  etag: 'etag-1',
};

const repositoryAsset = {
  asset_key: 'asset-roadmap',
  asset_type: 'workspace_document' as const,
  display_name: 'roadmap.md',
  source_label: 'customer-webdav',
  state_code: 'ready' as const,
  detail_text: 'Signed workspace document evidence',
  content_chars: 128,
  captured_at: '2026-09-06T00:00:00Z',
  evidence_source: 'signed-workspace',
  thread_key: 'thread-roadmap',
  provider_write_executed: false,
};

function buildProps(requestDocumentAction = vi.fn()) {
  return {
    writebackStatus: 'idle',
    writebackResult: null,
    requestWebdavWritebackIntent: vi.fn(),
    isWritebackLoading: false,
    canRequestWebdavWriteback: true,
    selectedWebdavAccount: webdavAccount,
    isWebdavSourceLoading: false,
    setSelectedWebdavSourceId: vi.fn(),
    uniqueThreadStatus: 'idle',
    uniqueThreadResult: null,
    requestUniqueThreadIntent: vi.fn(),
    isUniqueThreadLoading: false,
    connectorEvents: [],
    dataSurfaceStatus: 'ready' as const,
    dataQualitySurface: null,
    embeddingStage: null,
    emailRepository: { object_count: 0 },
    attachmentRepository: { object_count: 0 },
    handleEmailImportFileChange: vi.fn(),
    requestEmailFileImport: vi.fn(),
    isEmailImportLoading: false,
    emailImportFiles: [],
    emailImportStatus: 'idle' as const,
    emailImportResult: null,
    handleDocumentFileChange: vi.fn(),
    requestDocumentUpload: vi.fn(),
    documentActionPendingAction: null,
    documentUploadFiles: [],
    documentActionStatus: 'idle' as const,
    documentActionResult: null,
    webdavAccountStatus: 'ready' as const,
    webdavAccounts: [webdavAccount],
    webdavAccountMap: new Map([[webdavAccount.source_id, { account: webdavAccount, index: 0 }]]),
    projectFolders: [],
    selectedRepositoryAssetKey: repositoryAsset.asset_key,
    setSelectedRepositoryAssetKey: vi.fn(),
    repositoryAssets: [repositoryAsset],
    selectedWorkspaceDocument: { state_code: 'ready' },
    requestDocumentAction,
  };
}

describe('DocumentRepositoryTab WebDAV confirmation', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;

  afterEach(async () => {
    if (root) {
      await act(async () => root?.unmount());
    }
    document.body.style.overflow = '';
    container?.remove();
    container = null;
    root = null;
  });

  it('keeps focus and interaction inside the modal confirmation and restores the write trigger', async () => {
    const requestDocumentAction = vi.fn();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<DocumentRepositoryTab {...buildProps(requestDocumentAction)} />);
    });

    const findButton = (label: string) => Array.from(container?.querySelectorAll('button') ?? [])
      .find((button) => button.textContent?.includes(label));
    const writeTrigger = findButton('고객 WebDAV에 문서 쓰기');
    expect(writeTrigger).toBeDefined();
    writeTrigger?.focus();

    await act(async () => {
      writeTrigger?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const dialog = container?.querySelector('[role="alertdialog"]');
    const cancelButton = findButton('취소');
    const confirmButton = findButton('WebDAV 쓰기 확인');
    expect(dialog?.getAttribute('aria-modal')).toBe('true');
    expect(dialog?.parentElement?.className).toContain('fixed inset-0');
    expect(dialog?.previousElementSibling?.getAttribute('aria-hidden')).toBe('true');
    expect(document.body.style.overflow).toBe('hidden');
    expect(document.activeElement).toBe(cancelButton);

    confirmButton?.focus();
    await act(async () => {
      confirmButton?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    });
    expect(document.activeElement).toBe(cancelButton);

    cancelButton?.focus();
    await act(async () => {
      cancelButton?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }));
    });
    expect(document.activeElement).toBe(confirmButton);

    await act(async () => {
      confirmButton?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(container?.querySelector('[role="alertdialog"]')).toBeNull();
    expect(document.body.style.overflow).toBe('');
    expect(document.activeElement).toBe(writeTrigger);

    await act(async () => {
      writeTrigger?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      findButton('WebDAV 쓰기 확인')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(requestDocumentAction).toHaveBeenCalledWith('webdav-materialization-intent');
    expect(document.activeElement).toBe(writeTrigger);
  });

  it('locks WebDAV account and repository-asset selection while a document action is pending', async () => {
    const setSelectedWebdavSourceId = vi.fn();
    const setSelectedRepositoryAssetKey = vi.fn();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(
        <DocumentRepositoryTab
          {...buildProps()}
          documentActionPendingAction="reparse"
          setSelectedWebdavSourceId={setSelectedWebdavSourceId}
          setSelectedRepositoryAssetKey={setSelectedRepositoryAssetKey}
        />,
      );
    });

    const webdavAccountButton = Array.from(container.querySelectorAll('button'))
      .find((button) => button.textContent?.includes('Customer WebDAV'));
    expect(webdavAccountButton).toBeDefined();
    expect(webdavAccountButton?.disabled).toBe(true);

    const assetCard = container.querySelector('article[role="button"]');
    expect(assetCard?.getAttribute('aria-disabled')).toBe('true');
    await act(async () => {
      assetCard?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      assetCard?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      assetCard?.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
    });

    expect(setSelectedWebdavSourceId).not.toHaveBeenCalled();
    expect(setSelectedRepositoryAssetKey).not.toHaveBeenCalled();
  });
});
