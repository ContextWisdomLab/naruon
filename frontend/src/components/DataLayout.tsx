"use client";

import { useCallback, useState, useEffect, useMemo, type ChangeEvent, type KeyboardEvent } from 'react';
import { Database } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

import { DocumentRepositoryTab } from './data-layout/DocumentRepositoryTab';
import { IngestionPipelineTab } from './data-layout/IngestionPipelineTab';
import { EmbeddingTab } from './data-layout/EmbeddingTab';
import { QualityCheckTab } from './data-layout/QualityCheckTab';
import {
  WebdavWritebackIntentResponse,
  WritebackStatus,
  WebdavAccountStatus,
  WebdavAccount,
  WebdavAccountLookup,
  UniqueThreadIntentResponse,
  UniqueThreadStatus,
  EmailImportStatus,
  DocumentActionStatus,
  DataSurfaceStatus,
  DataEvidenceSnapshotResponse,
  DataQualitySurfaceResponse,
  EmailFileImportResponse,
  DataDocumentActionResponse,
  DocumentActionKind,
  duplicateImportCandidates
} from './data-layout/types';
import {
  getApiErrorStatus,
  getSafeErrorSummary,
  getDocumentTypeForFile,
  isTextDocumentUploadType,
} from './data-layout/utils';


const DATA_TABS = ['문서 저장소', '수집 파이프라인', '임베딩', '품질 점검'] as const;
type DataTab = (typeof DATA_TABS)[number];

function dataTabId(tab: DataTab) {
  return `data-tab-${DATA_TABS.indexOf(tab)}`;
}

function dataTabPanelId(tab: DataTab) {
  return `data-panel-${DATA_TABS.indexOf(tab)}`;
}

export function DataLayout() {
  const [activeTab, setActiveTab] = useState<DataTab>('문서 저장소');
  
  interface ProjectFolder {
    folder_uid: string;
    project_name: string;
    webdav_path: string;
  }
  
  const [webdavAccounts, setWebdavAccounts] = useState<WebdavAccount[]>([]);
  const [webdavAccountStatus, setWebdavAccountStatus] = useState<WebdavAccountStatus>('loading');
  const [selectedWebdavSourceId, setSelectedWebdavSourceId] = useState<string | null>(null);
  const [projectFolders, setProjectFolders] = useState<ProjectFolder[]>([]);
  const [writebackStatus, setWritebackStatus] = useState<WritebackStatus>('idle');
  const [writebackResult, setWritebackResult] = useState<WebdavWritebackIntentResponse | null>(null);
  const [uniqueThreadStatus, setUniqueThreadStatus] = useState<UniqueThreadStatus>('idle');
  const [uniqueThreadResult, setUniqueThreadResult] = useState<UniqueThreadIntentResponse | null>(null);
  const [emailImportStatus, setEmailImportStatus] = useState<EmailImportStatus>('idle');
  const [emailImportResult, setEmailImportResult] = useState<EmailFileImportResponse | null>(null);
  const [emailImportFiles, setEmailImportFiles] = useState<File[]>([]);
  const [documentActionStatus, setDocumentActionStatus] = useState<DocumentActionStatus>('idle');
  const [documentActionPendingAction, setDocumentActionPendingAction] = useState<DocumentActionKind | null>(null);
  const [documentActionResult, setDocumentActionResult] = useState<DataDocumentActionResponse | null>(null);
  const [documentUploadFiles, setDocumentUploadFiles] = useState<File[]>([]);
  const [dataSurfaceStatus, setDataSurfaceStatus] = useState<DataSurfaceStatus>('loading');
  const [dataQualitySurface, setDataQualitySurface] = useState<DataQualitySurfaceResponse | null>(null);
  const [dataEvidenceSnapshot, setDataEvidenceSnapshot] = useState<DataEvidenceSnapshotResponse | null>(null);
  const [selectedRepositoryAssetKey, setSelectedRepositoryAssetKey] = useState<string | null>(null);

  const webdavAccountMap = useMemo<WebdavAccountLookup>(
    () => new Map(webdavAccounts.map((account, index) => [
      account.source_id,
      { account, index },
    ])),
    [webdavAccounts],
  );

  const loadDataEvidenceSnapshot = useCallback(async () => {
    try {
      const snapshot = await apiClient.get<DataEvidenceSnapshotResponse>('/api/data/quality-surface/evidence-snapshot');
      if (
        snapshot.snapshot_version !== 'data_quality_evidence_snapshot.v1'
        || snapshot.privacy_redaction_policy.raw_content_exposed !== false
      ) {
        throw new Error('Invalid evidence snapshot response');
      }
      setDataEvidenceSnapshot(snapshot);
      return snapshot;
    } catch (error: unknown) {
      console.error('Data evidence snapshot fetch error', getSafeErrorSummary(error));
      setDataEvidenceSnapshot(null);
      return null;
    }
  }, []);

  const loadDataQualitySurface = useCallback(async () => {
    try {
      const [data] = await Promise.all([
        apiClient.get<DataQualitySurfaceResponse>('/api/data/quality-surface'),
        loadDataEvidenceSnapshot(),
      ]);
      if (!Array.isArray(data.repositories) || !Array.isArray(data.pipeline_stages)) {
        throw new Error('Invalid data quality surface response');
      }
      setDataQualitySurface(data);
      setDataSurfaceStatus('ready');
    } catch (error: unknown) {
      console.error('Data quality surface fetch error', getSafeErrorSummary(error));
      setDataQualitySurface(null);
      setDataEvidenceSnapshot(null);
      setDataSurfaceStatus('error');
    }
  }, [loadDataEvidenceSnapshot]);

  useEffect(() => {
    const dataQualitySurfaceTimer = window.setTimeout(() => {
      void loadDataQualitySurface();
    }, 0);

    apiClient.get<WebdavAccount[]>('/api/webdav/accounts')
      .then((data) => {
        if (!Array.isArray(data)) throw new Error('Invalid WebDAV accounts response');
        setWebdavAccounts(data);
        setSelectedWebdavSourceId(data.find((account) => account.writeback_enabled)?.source_id ?? null);
        setWebdavAccountStatus('ready');
      })
      .catch((error: unknown) => {
        console.error('WebDAV accounts fetch error', getSafeErrorSummary(error));
        setWebdavAccounts([]);
        setWebdavAccountStatus('error');
        setSelectedWebdavSourceId(null);
      });

    apiClient.get<ProjectFolder[]>('/api/webdav/folders')
      .then(data => Array.isArray(data) && setProjectFolders(data))
      .catch((error: unknown) => console.error('WebDAV folders fetch error', getSafeErrorSummary(error)));

    return () => window.clearTimeout(dataQualitySurfaceTimer);
  }, [loadDataQualitySurface]);

  const requestWebdavWritebackIntent = useCallback(async () => {
    setWritebackStatus('loading');
    setWritebackResult(null);
    try {
      if (webdavAccountStatus !== 'ready') {
        setWritebackStatus('fetch_error');
        return;
      }
      const targetSourceId = webdavAccounts.find((account) => (
        account.source_id === selectedWebdavSourceId && account.writeback_enabled
      ))?.source_id ?? webdavAccounts.find((account) => account.writeback_enabled)?.source_id;
      if (!targetSourceId) {
        setWritebackStatus('no_source');
        return;
      }
      const result = await apiClient.post<WebdavWritebackIntentResponse>(
        '/api/webdav/writeback-intent',
        { target_source_id: targetSourceId },
      );
      setWritebackResult(result);
      setWritebackStatus('success');
    } catch (error: unknown) {
      const status = getApiErrorStatus(error);
      if (status === 422) {
        setWritebackStatus('no_source');
      } else if (status === 409) {
        setWritebackStatus('conflict');
      } else if (status === 401 || status === 403) {
        setWritebackStatus('auth');
      } else {
        setWritebackStatus('error');
      }
    }
  }, [selectedWebdavSourceId, webdavAccounts, webdavAccountStatus]);

  const requestUniqueThreadIntent = useCallback(async () => {
    setUniqueThreadStatus('loading');
    setUniqueThreadResult(null);
    try {
      const result = await apiClient.post<UniqueThreadIntentResponse>(
        '/api/emails/unique-thread-intent',
        { candidates: duplicateImportCandidates },
      );
      setUniqueThreadResult(result);
      setUniqueThreadStatus('success');
    } catch (error: unknown) {
      const status = getApiErrorStatus(error);
      setUniqueThreadStatus(status === 401 || status === 403 ? 'auth' : 'error');
    }
  }, []);

  const handleEmailImportFileChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setEmailImportFiles(Array.from(event.target.files ?? []));
    setEmailImportResult(null);
    setEmailImportStatus('idle');
  }, []);

  const requestEmailFileImport = useCallback(async () => {
    if (emailImportFiles.length === 0) {
      setEmailImportStatus('error');
      return;
    }

    setEmailImportStatus('loading');
    setEmailImportResult(null);
    try {
      const formData = new FormData();
      emailImportFiles.forEach((file) => formData.append('files', file));
      const result = await apiClient.postForm<EmailFileImportResponse>('/api/emails/import-files', formData);
      setEmailImportResult(result);
      setEmailImportStatus('success');
    } catch (error: unknown) {
      const status = getApiErrorStatus(error);
      setEmailImportStatus(status === 401 || status === 403 ? 'auth' : 'error');
    }
  }, [emailImportFiles]);

  const handleDocumentFileChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDocumentUploadFiles(Array.from(event.target.files ?? []));
    setDocumentActionResult(null);
    setDocumentActionStatus('idle');
  }, []);

  const requestDocumentUpload = useCallback(async () => {
    const [file] = documentUploadFiles;
    if (!file) {
      setDocumentActionPendingAction(null);
      setDocumentActionStatus('error');
      return;
    }

    // 50MB file size limit
    if (file.size > 50 * 1024 * 1024) {
      setDocumentActionPendingAction(null);
      setDocumentActionStatus('error');
      return;
    }

    setDocumentActionPendingAction('upload');
    setDocumentActionStatus('loading');
    setDocumentActionResult(null);
    try {
      const documentType = getDocumentTypeForFile(file);
      if (!isTextDocumentUploadType(documentType)) {
        setDocumentActionPendingAction(null);
        setDocumentActionStatus('error');
        return;
      }
      const documentContent = await file.text();
      const result = await apiClient.post<DataDocumentActionResponse>(
        '/api/data/documents',
        {
          document_name: file.name,
          document_type: documentType,
          document_content: documentContent,
        },
      );
      setDocumentActionResult(result);
      setDocumentActionPendingAction(null);
      setDocumentActionStatus('success');
      setDataSurfaceStatus('loading');
      await loadDataQualitySurface();
    } catch (error: unknown) {
      const status = getApiErrorStatus(error);
      setDocumentActionPendingAction(null);
      setDocumentActionStatus(status === 401 || status === 403 ? 'auth' : 'error');
    }
  }, [documentUploadFiles, loadDataQualitySurface]);

  const requestDocumentAction = useCallback(async (
    action: Exclude<DocumentActionKind, 'upload'>,
  ) => {
    const asset = dataQualitySurface?.repository_assets.find((candidate) => (
      candidate.asset_key === selectedRepositoryAssetKey
    )) ?? dataQualitySurface?.repository_assets[0] ?? null;
    if (!asset || asset.asset_type !== 'workspace_document') {
      setDocumentActionPendingAction(null);
      setDocumentActionStatus('error');
      return;
    }
    const targetSourceId = webdavAccounts.find((account) => (
      account.source_id === selectedWebdavSourceId && account.writeback_enabled
    ))?.source_id ?? webdavAccounts.find((account) => account.writeback_enabled)?.source_id;
    if (action === 'webdav-materialization-intent' && (webdavAccountStatus !== 'ready' || !targetSourceId)) {
      setDocumentActionPendingAction(null);
      setDocumentActionStatus('error');
      return;
    }

    setDocumentActionPendingAction(action);
    setDocumentActionStatus('loading');
    setDocumentActionResult(null);
    try {
      const result = await apiClient.post<DataDocumentActionResponse>(
        `/api/data/documents/${encodeURIComponent(asset.asset_key)}/${action}`,
        action === 'webdav-materialization-intent'
          ? { target_source_id: targetSourceId, execute_provider: true }
          : {},
      );
      setDocumentActionResult(result);
      setDocumentActionPendingAction(null);
      if (action === 'webdav-materialization-intent' && !result.provider_write_executed) {
        setDocumentActionStatus('connector_error');
        return;
      }
      setDocumentActionStatus('success');
      setDataSurfaceStatus('loading');
      await loadDataQualitySurface();
    } catch (error: unknown) {
      const status = getApiErrorStatus(error);
      setDocumentActionPendingAction(null);
      setDocumentActionStatus(
        status === 401 || status === 403
          ? 'auth'
          : status === 409
            ? 'conflict'
            : status === 422
              ? 'invalid'
              : 'error',
      );
    }
  }, [
    dataQualitySurface,
    loadDataQualitySurface,
    selectedRepositoryAssetKey,
    selectedWebdavSourceId,
    webdavAccounts,
    webdavAccountStatus,
  ]);

  const isWritebackLoading = writebackStatus === 'loading';
  const isWebdavSourceLoading = webdavAccountStatus === 'loading';
  const canRequestWebdavWriteback = webdavAccountStatus === 'ready';
  const isUniqueThreadLoading = uniqueThreadStatus === 'loading';
  const isEmailImportLoading = emailImportStatus === 'loading';
  const selectedWebdavAccount = webdavAccounts.find((account) => (
    account.source_id === selectedWebdavSourceId && account.writeback_enabled
  )) ?? webdavAccounts.find((account) => account.writeback_enabled) ?? null;
  const repositories = dataQualitySurface?.repositories ?? [];
  const emailRepository = repositories.find((repository) => repository.repository_type === 'email_repository');
  const attachmentRepository = repositories.find((repository) => repository.repository_type === 'attachment_repository');
  const embeddingStage = dataQualitySurface?.pipeline_stages.find((stage) => stage.stage_key === 'embedding_inventory');
  const connectorEvents = dataQualitySurface?.connector_events ?? [];
  const repositoryAssets = dataQualitySurface?.repository_assets ?? [];
  const selectedRepositoryAsset = repositoryAssets.find((asset) => asset.asset_key === selectedRepositoryAssetKey)
    ?? repositoryAssets[0]
    ?? null;
  const selectedWorkspaceDocument = selectedRepositoryAsset?.asset_type === 'workspace_document'
    ? selectedRepositoryAsset
    : null;

  const handleDataTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tab: DataTab) => {
    const currentIndex = DATA_TABS.indexOf(tab);
    let nextIndex: number;

    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowRight':
        nextIndex = (currentIndex + 1) % DATA_TABS.length;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        nextIndex = (currentIndex - 1 + DATA_TABS.length) % DATA_TABS.length;
        break;
      case 'Home':
        nextIndex = 0;
        break;
      case 'End':
        nextIndex = DATA_TABS.length - 1;
        break;
      default:
        return;
    }

    event.preventDefault();
    setActiveTab(DATA_TABS[nextIndex]);
    event.currentTarget.parentElement
      ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
      [nextIndex]?.focus();
  };

  return (
    <div className="flex h-full min-w-0 min-h-0 bg-background text-foreground overflow-x-hidden">
      {/* Local navigation (LNB): desktop left sidebar for the data domain's areas */}
      <nav
        aria-label="데이터 로컬 탐색"
        className="hidden w-60 shrink-0 flex-col gap-1 border-r border-border bg-card p-4 lg:flex"
      >
        <h1 className="mb-2 flex items-center gap-2 px-2 text-lg font-bold">
          <Database className="size-5 text-primary" aria-hidden="true" />
          <span>데이터와 파일</span>
        </h1>
        <div role="tablist" aria-label="데이터 보기" aria-orientation="vertical" className="flex flex-col gap-1">
          {DATA_TABS.map((tab) => (
            <button
              id={dataTabId(tab)}
              type="button"
              key={tab}
              role="tab"
              aria-controls={dataTabPanelId(tab)}
              aria-selected={activeTab === tab}
              tabIndex={activeTab === tab ? 0 : -1}
              onClick={() => setActiveTab(tab)}
              onKeyDown={(event) => handleDataTabKeyDown(event, tab)}
              className={`rounded-lg px-3 py-2 text-left text-sm font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${activeTab === tab ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary'}`}
            >
              {tab}
            </button>
          ))}
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Mobile local tabs: the LNB collapses to a horizontal tab strip below the desktop breakpoint */}
        <header className="flex h-16 shrink-0 items-center border-b border-border bg-card px-4 lg:hidden">
          <h1 className="sr-only">데이터와 파일</h1>
          <div role="tablist" aria-label="데이터 보기" className="flex flex-1 min-w-0 gap-2 overflow-x-auto pb-1 scrollbar-hide">
            {DATA_TABS.map((tab) => (
              <button
                id={`mobile-${dataTabId(tab)}`}
                type="button"
                key={tab}
                role="tab"
                aria-controls={dataTabPanelId(tab)}
                aria-selected={activeTab === tab}
                tabIndex={activeTab === tab ? 0 : -1}
                onClick={() => setActiveTab(tab)}
                onKeyDown={(event) => handleDataTabKeyDown(event, tab)}
                className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm font-bold transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${activeTab === tab ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-secondary'}`}
              >
                {tab}
              </button>
            ))}
          </div>
        </header>

        <main className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden p-4 pb-[calc(7rem+env(safe-area-inset-bottom))] md:p-8 bg-background">
        <div
          id={dataTabPanelId(activeTab)}
          role="tabpanel"
          aria-labelledby={dataTabId(activeTab)}
          className="max-w-5xl mx-auto space-y-8"
        >
          
          {activeTab === '문서 저장소' && (
            <DocumentRepositoryTab
              dataSurfaceStatus={dataSurfaceStatus}
              dataQualitySurface={dataQualitySurface}
              embeddingStage={embeddingStage}
              emailRepository={emailRepository}
              attachmentRepository={attachmentRepository}
              handleEmailImportFileChange={handleEmailImportFileChange}
              requestEmailFileImport={requestEmailFileImport}
              isEmailImportLoading={isEmailImportLoading}
              emailImportFiles={emailImportFiles}
              emailImportStatus={emailImportStatus}
              emailImportResult={emailImportResult}
              handleDocumentFileChange={handleDocumentFileChange}
              requestDocumentUpload={requestDocumentUpload}
              documentActionPendingAction={documentActionPendingAction}
              documentUploadFiles={documentUploadFiles}
              documentActionStatus={documentActionStatus}
              documentActionResult={documentActionResult}
              webdavAccountStatus={webdavAccountStatus}
              webdavAccounts={webdavAccounts}
              webdavAccountMap={webdavAccountMap}
              projectFolders={projectFolders}
              selectedRepositoryAssetKey={selectedRepositoryAssetKey}
              setSelectedRepositoryAssetKey={setSelectedRepositoryAssetKey}
              repositoryAssets={repositoryAssets}
              selectedWorkspaceDocument={selectedWorkspaceDocument}
              requestDocumentAction={requestDocumentAction}
              connectorEvents={connectorEvents}
              writebackStatus={writebackStatus}
              writebackResult={writebackResult}
              requestWebdavWritebackIntent={requestWebdavWritebackIntent}
              isWritebackLoading={isWritebackLoading}
              canRequestWebdavWriteback={canRequestWebdavWriteback}
              selectedWebdavAccount={selectedWebdavAccount}
              isWebdavSourceLoading={isWebdavSourceLoading}
              setSelectedWebdavSourceId={setSelectedWebdavSourceId}
              uniqueThreadStatus={uniqueThreadStatus}
              uniqueThreadResult={uniqueThreadResult}
              requestUniqueThreadIntent={requestUniqueThreadIntent}
              isUniqueThreadLoading={isUniqueThreadLoading}
            />
          )}

          {activeTab === '수집 파이프라인' && (
            <IngestionPipelineTab
              dataSurfaceStatus={dataSurfaceStatus}
              dataQualitySurface={dataQualitySurface}
            />
          )}

          {activeTab === '임베딩' && (
            <EmbeddingTab
              dataSurfaceStatus={dataSurfaceStatus}
              dataQualitySurface={dataQualitySurface}
            />
          )}

          {activeTab === '품질 점검' && (
            <QualityCheckTab
              dataSurfaceStatus={dataSurfaceStatus}
              dataQualitySurface={dataQualitySurface}
              dataEvidenceSnapshot={dataEvidenceSnapshot}
            />
          )}
        </div>
      </main>
      </div>
    </div>
  );
}
