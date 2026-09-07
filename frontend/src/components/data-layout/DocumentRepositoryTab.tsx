/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState, type ChangeEvent } from 'react';
import { HardDrive, Upload, Loader2, FileText, FolderOpen, Database, RefreshCw, CheckCircle2, Server } from 'lucide-react';
import { toSafeReactText } from '@/lib/safe-text';
import {
  DataQualitySurfaceResponse,
  EmailImportStatus,
  DocumentActionStatus,
  EmailFileImportResponse,
  DataDocumentActionResponse,
  DocumentActionKind,
  WebdavAccountStatus,
  WebdavAccount,
  WebdavAccountLookup,
  DataSurfaceStatus
} from './types';
import {
  formatCount,
  getWriteBoundaryLabel,
  formatDataTimestamp,
  getAssetEvidenceLabel,
  getSourceReadinessLabel,
  getWebdavAccountLabel,
  getSurfaceStatusLabel,
  getWritebackTargetLabel
} from './utils';

interface DocumentRepositoryTabProps {
  writebackStatus: any;
  writebackResult: any;
  requestWebdavWritebackIntent: () => void;
  isWritebackLoading: boolean;
  canRequestWebdavWriteback: boolean;
  selectedWebdavAccount: any;
  isWebdavSourceLoading: boolean;
  setSelectedWebdavSourceId: (id: string | null) => void;
  uniqueThreadStatus: any;
  uniqueThreadResult: any;
  requestUniqueThreadIntent: () => void;
  isUniqueThreadLoading: boolean;

  connectorEvents: any[];
  dataSurfaceStatus: DataSurfaceStatus;
  dataQualitySurface: DataQualitySurfaceResponse | null;
  embeddingStage: any;
  emailRepository: any;
  attachmentRepository: any;
  handleEmailImportFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  requestEmailFileImport: () => void;
  isEmailImportLoading: boolean;
  emailImportFiles: File[];
  emailImportStatus: EmailImportStatus;
  emailImportResult: EmailFileImportResponse | null;
  handleDocumentFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  requestDocumentUpload: () => void;
  documentActionPendingAction: DocumentActionKind | null;
  documentUploadFiles: File[];
  documentActionStatus: DocumentActionStatus;
  documentActionResult: DataDocumentActionResponse | null;
  webdavAccountStatus: WebdavAccountStatus;
  webdavAccounts: WebdavAccount[];
  webdavAccountMap: WebdavAccountLookup;
  projectFolders: any[];
  selectedRepositoryAssetKey: string | null;
  setSelectedRepositoryAssetKey: (key: string | null) => void;
  repositoryAssets: any[];
  selectedWorkspaceDocument: any;
  requestDocumentAction: (action: Exclude<DocumentActionKind, 'upload'>) => void;
}

export function DocumentRepositoryTab({
  dataSurfaceStatus,
  dataQualitySurface,
  embeddingStage,
  emailRepository,
  attachmentRepository,
  handleEmailImportFileChange,
  requestEmailFileImport,
  isEmailImportLoading,
  emailImportFiles,
  emailImportStatus,
  emailImportResult,
  handleDocumentFileChange,
  requestDocumentUpload,
  documentActionPendingAction,
  documentUploadFiles,
  documentActionStatus,
  documentActionResult,
  webdavAccountStatus,
  webdavAccounts,
  webdavAccountMap,
  projectFolders,
  selectedRepositoryAssetKey,
  setSelectedRepositoryAssetKey,
  repositoryAssets,
  selectedWorkspaceDocument,
  requestDocumentAction,
  connectorEvents,

  writebackStatus,
  writebackResult,
  requestWebdavWritebackIntent,
  isWritebackLoading,
  canRequestWebdavWriteback,
  selectedWebdavAccount,
  isWebdavSourceLoading,
  setSelectedWebdavSourceId,
  uniqueThreadStatus,
  uniqueThreadResult,
  requestUniqueThreadIntent,
  isUniqueThreadLoading,
}: DocumentRepositoryTabProps) {
  const [webdavWriteConfirmationKey, setWebdavWriteConfirmationKey] = useState<string | null>(null);

  const selectedRepositoryAsset = repositoryAssets.find((asset) => asset.asset_key === selectedRepositoryAssetKey)
    ?? repositoryAssets[0]
    ?? null;
  const selectedWebdavAccountIndex = webdavAccounts.findIndex((account) => account.source_id === selectedWebdavAccount?.source_id);
  const selectedWebdavAccountLabel = selectedWebdavAccount
    ? getWebdavAccountLabel(selectedWebdavAccount, Math.max(selectedWebdavAccountIndex, 0))
    : '선택된 WebDAV 저장소';
  const currentWebdavWriteConfirmationKey = `${selectedRepositoryAsset?.asset_key ?? ''}:${selectedWebdavAccount?.source_id ?? ''}`;
return (
<div className="space-y-6">
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="rounded-xl bg-blue-100 p-3"><HardDrive className="size-5 text-blue-700" /></div>
                    <div>
                      <h2 className="font-bold text-sm text-muted-foreground">메일/첨부 저장소</h2>
                      <p className="text-xl font-bold">
                        {dataSurfaceStatus === 'loading' ? '확인 중' : `${formatCount(emailRepository?.object_count ?? 0)} / ${formatCount(attachmentRepository?.object_count ?? 0)}`}
                      </p>
                      <p className="mt-1 text-xs font-semibold text-muted-foreground">메일 / 첨부</p>
                    </div>
                  </div>
                  <div className="h-2 w-full rounded-full bg-border overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all"
                      style={{ width: `${embeddingStage?.progress_percent ?? 0}%` }}
                    ></div>
                  </div>
                  <div className="mt-4 grid gap-3">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                      <label className="inline-flex min-h-9 cursor-pointer items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs font-bold text-foreground hover:bg-secondary sm:w-fit">
                        <Upload className="size-4" />
                        이메일 파일 선택
                        <input
                          type="file"
                          multiple
                          accept=".eml,.zip,.mbox,message/rfc822,application/zip,application/mbox"
                          className="sr-only"
                          onChange={handleEmailImportFileChange}
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => void requestEmailFileImport()}
                        disabled={isEmailImportLoading || emailImportFiles.length === 0}
                        aria-busy={isEmailImportLoading}
                        className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-bold text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60 sm:w-fit"
                      >
                        {isEmailImportLoading ? (
                          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        ) : (
                          <Upload className="size-4" />
                        )}
                        {isEmailImportLoading ? '반입 중' : '선택 파일 반입'}
                      </button>
                    </div>
                    <div role="status" aria-live="polite" className="text-xs font-semibold text-muted-foreground">
                      {emailImportStatus === 'idle' && emailImportFiles.length === 0 && 'EML, ZIP, MBOX 원본을 선택해 메일/첨부 근거로 수집합니다.'}
                      {emailImportStatus === 'idle' && emailImportFiles.length > 0 && `${formatCount(emailImportFiles.length)}개 파일 선택됨`}
                      {emailImportStatus === 'loading' && '이메일 원본 파일을 반입하는 중입니다.'}
                      {emailImportStatus === 'auth' && <span className="font-bold text-red-700">signed session이 필요합니다. 공개 identity header로는 이메일 원본을 반입할 수 없습니다.</span>}
                      {emailImportStatus === 'error' && <span className="font-bold text-red-700">이메일 원본 파일 반입에 실패했습니다.</span>}
                      {emailImportStatus === 'success' && emailImportResult && (
                        <span className="text-foreground">
                          {formatCount(emailImportResult.imported_count)}개 반입 · 중복 {formatCount(emailImportResult.skipped_count)}개 · 실패 {formatCount(emailImportResult.failed_count)}개 · 첨부 {formatCount(emailImportResult.attachment_count)}개 · {getWriteBoundaryLabel(emailImportResult.provider_write_executed)}
                        </span>
                      )}
                    </div>
                    <div className="mt-2 flex flex-col gap-2 border-t border-border pt-3 sm:flex-row sm:items-center">
                      <label className="inline-flex min-h-9 cursor-pointer items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs font-bold text-foreground hover:bg-secondary sm:w-fit">
                        <FileText className="size-4" />
                        문서 원본 선택
                        <input
                          type="file"
                          accept=".txt,.md,.markdown,text/plain,text/markdown"
                          className="sr-only"
                          disabled={documentActionPendingAction !== null}
                          onChange={handleDocumentFileChange}
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => void requestDocumentUpload()}
                        disabled={documentActionPendingAction !== null || documentUploadFiles.length === 0}
                        aria-busy={documentActionPendingAction === 'upload'}
                        className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-bold text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60 sm:w-fit"
                      >
                        {documentActionPendingAction === 'upload' ? (
                          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        ) : (
                          <Upload className="size-4" />
                        )}
                        {documentActionPendingAction === 'upload' ? '저장 중' : '선택 문서 저장'}
                      </button>
                    </div>
                    <div role="status" aria-live="polite" className="text-xs font-semibold text-muted-foreground">
                      {documentActionStatus === 'idle' && documentUploadFiles.length === 0 && '텍스트, Markdown, HWP 원본을 워크스페이스 문서 근거로 저장합니다.'}
                      {documentActionStatus === 'idle' && documentUploadFiles.length > 0 && `${documentUploadFiles[0]?.name ?? '문서'} 선택됨`}
                      {documentActionStatus === 'loading' && '문서 작업을 처리하는 중입니다.'}
                      {documentActionStatus === 'auth' && <span className="font-bold text-red-700">로그인이 만료되었습니다. 다시 로그인한 후 재시도하세요.</span>}
                      {documentActionStatus === 'conflict' && <span className="font-bold text-amber-700">문서 처리가 아직 끝나지 않았습니다. 처리가 완료된 후 재시도하세요.</span>}
                      {documentActionStatus === 'invalid' && <span className="font-bold text-amber-700">쓸 수 있는 문서 내용 또는 WebDAV 저장소를 확인한 후 재시도하세요.</span>}
                      {documentActionStatus === 'connector_error' && <span className="font-bold text-red-700">WebDAV 쓰기를 완료하지 못했습니다. 연결 상태를 확인한 후 재시도하거나 관리자에게 문의하세요.</span>}
                      {documentActionStatus === 'error' && <span className="font-bold text-red-700">문서 작업을 완료하지 못했습니다. 잠시 후 재시도하세요.</span>}
                      {documentActionStatus === 'success' && documentActionResult && (
                        <span className="text-foreground">
                          {toSafeReactText(documentActionResult.document_name)} · {toSafeReactText(documentActionResult.message)} · {getWriteBoundaryLabel(documentActionResult.provider_write_executed)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="rounded-xl bg-green-100 p-3"><FolderOpen className="size-5 text-green-700" /></div>
                    <div>
                      <h2 className="font-bold text-sm text-muted-foreground">WebDAV 원본 (연동됨)</h2>
                      <p className="text-xl font-bold">
                        {webdavAccounts.length > 0 ? `${webdavAccounts.length}개 계정` : '연결 없음'}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-2">
                    {webdavAccounts.map((account, index) => {
                      const accountSelected = selectedWebdavAccount?.source_id === account.source_id;



  return (
                        <button
                          key={account.source_id}
                          type="button"
                          disabled={!account.writeback_enabled}
                          aria-pressed={accountSelected}
                          onClick={() => setSelectedWebdavSourceId(account.source_id)}
                          className={`flex min-w-0 items-start gap-2 rounded-lg border p-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-70 ${
                            accountSelected ? 'border-primary bg-primary/10' : 'border-transparent bg-secondary/50 hover:border-primary/40'
                          }`}
                        >
                          <Server className="mt-0.5 size-4 shrink-0 text-primary" />
                          <span className="min-w-0">
                            <span className="block break-all font-medium text-foreground">{getWebdavAccountLabel(account, index)}
</span>
                            <span className="block break-all text-xs text-muted-foreground">
                              {getSourceReadinessLabel(account)}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm flex items-center justify-between">
                  <div>
                    <h2 className="font-bold text-sm text-muted-foreground mb-1">인덱싱 상태</h2>
                    <p className="text-lg font-bold text-emerald-600 flex items-center gap-2">
                      <CheckCircle2 className="size-5" />
                      {embeddingStage ? getSurfaceStatusLabel(embeddingStage.status_code) : dataSurfaceStatus === 'error' ? '확인 실패' : '확인 중'}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {dataQualitySurface ? '감사 근거 기록됨' : '감사 근거 확인 중'}
                    </p>
                  </div>
                  <span className="rounded-lg border border-border bg-background px-3 py-2 text-xs font-bold shadow-sm">
                    {getWriteBoundaryLabel(dataQualitySurface?.provider_write_executed ?? false)}
                  </span>
                </div>
	              </div>

              <section aria-label="문서 저장소 파일 자산" className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
                <div className="flex flex-col gap-3 border-b border-border bg-secondary/30 p-5 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="font-bold text-lg flex items-center gap-2"><FileText className="size-5" /> 최근 파일/첨부 자산</h2>
                    <p className="mt-1 text-sm text-muted-foreground">메일 첨부에서 파생된 문서 자산을 원본 메일/스레드 근거와 함께 추적합니다.</p>
                  </div>
                  <span className="w-fit rounded-lg border border-border bg-background px-3 py-2 text-xs font-bold">
                    {formatCount(repositoryAssets.length)}개 자산
                  </span>
                </div>
                <div className="grid gap-3 p-4">
                  {dataSurfaceStatus === 'loading' && (
                    <p className="text-sm font-semibold text-muted-foreground">문서 자산 근거를 확인하는 중입니다.</p>
                  )}
                  {dataSurfaceStatus === 'error' && (
                    <p className="text-sm font-bold text-red-700">문서 자산 근거를 불러오지 못했습니다.</p>
                  )}
                  {dataSurfaceStatus === 'ready' && repositoryAssets.length === 0 && (
                    <p className="text-sm text-muted-foreground">이 워크스페이스에 원본 연결 첨부 자산이 아직 없습니다.</p>
                  )}
                  {repositoryAssets.map((asset) => {
                    const assetSelected = selectedRepositoryAsset?.asset_key === asset.asset_key;



  return (
                    <article
                      key={asset.asset_key}
                      role="button"
                      tabIndex={0}
                      aria-pressed={assetSelected}
                      onClick={() => setSelectedRepositoryAssetKey(asset.asset_key)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setSelectedRepositoryAssetKey(asset.asset_key);
                        }
                      }}
                      className={`cursor-pointer rounded-xl border bg-background p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                        assetSelected ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'
                      }`}
                    >
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0">
                          <div className="flex min-w-0 items-start gap-3">
                            <FileText className="mt-0.5 size-5 shrink-0 text-primary" />
                            <div className="min-w-0">
                              <h3 className="break-all text-sm font-black">{toSafeReactText(asset.display_name)}</h3>
                              <p className="mt-1 break-all text-xs text-muted-foreground">{toSafeReactText(asset.source_label)}</p>
                            </div>
                          </div>
                        </div>
                        <span className={`w-fit shrink-0 rounded-full px-2 py-1 text-xs font-bold ${asset.state_code === 'ready' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'}`}>
                          {asset.state_code === 'ready' ? '정상' : '점검 필요'}
                        </span>
                      </div>
                      <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                        <div>
                          <dt className="font-black text-muted-foreground">근거 상태</dt>
                          <dd className="mt-1 text-sm font-bold">{getAssetEvidenceLabel(asset)}</dd>
                        </div>
                        <div>
                          <dt className="font-black text-muted-foreground">본문 길이</dt>
                          <dd className="mt-1 text-sm font-bold">{formatCount(asset.content_chars)}자</dd>
                        </div>
                        <div>
                          <dt className="font-black text-muted-foreground">수집 시간</dt>
                          <dd className="mt-1 break-all text-sm font-bold">{formatDataTimestamp(asset.captured_at)}</dd>
                        </div>
                        <div>
                          <dt className="font-black text-muted-foreground">쓰기 경계</dt>
                          <dd className="mt-1 text-sm font-bold">{getWriteBoundaryLabel(asset.provider_write_executed)}</dd>
                        </div>
                        <div className="min-w-0 sm:col-span-2 lg:col-span-4">
                          <dt className="font-black text-muted-foreground">원본 근거</dt>
                          <dd className="mt-1 break-words text-sm font-semibold text-muted-foreground">{toSafeReactText(asset.detail_text)}</dd>
                        </div>
                      </dl>
                    </article>
                  );
                  })}
                </div>
              </section>

              {selectedRepositoryAsset && (
                <section aria-label="선택한 파일 자산 상세" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-xs font-black text-primary">선택한 원본 자산</p>
                      <h2 className="mt-1 break-all text-lg font-black">{toSafeReactText(selectedRepositoryAsset.display_name)}</h2>
                      <p className="mt-1 break-all text-sm text-muted-foreground">{toSafeReactText(selectedRepositoryAsset.source_label)}</p>
                    </div>
                    <span className={`w-fit shrink-0 rounded-full px-2 py-1 text-xs font-bold ${
                      selectedRepositoryAsset.state_code === 'ready' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'
                    }`}>
                      {selectedRepositoryAsset.state_code === 'ready' ? '정상' : '점검 필요'}
                    </span>
                  </div>
                  {selectedWorkspaceDocument && (
                    <>
                    <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                      <button
                        type="button"
                        onClick={() => void requestDocumentAction('reparse')}
                        disabled={documentActionPendingAction !== null}
                        aria-busy={documentActionPendingAction === 'reparse'}
                        className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs font-bold text-foreground hover:bg-secondary disabled:cursor-wait disabled:opacity-60"
                      >
                        {documentActionPendingAction === 'reparse' ? (
                          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        ) : (
                          <RefreshCw className="size-4" />
                        )}
                        {documentActionPendingAction === 'reparse' ? '상태 변경 중' : '파싱 완료로 표시'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void requestDocumentAction('embedding-regeneration-intent')}
                        disabled={documentActionPendingAction !== null}
                        aria-busy={documentActionPendingAction === 'embedding-regeneration-intent'}
                        className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs font-bold text-foreground hover:bg-secondary disabled:cursor-wait disabled:opacity-60"
                      >
                        {documentActionPendingAction === 'embedding-regeneration-intent' ? (
                          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        ) : (
                          <Database className="size-4" />
                        )}
                        {documentActionPendingAction === 'embedding-regeneration-intent' ? '요청 등록 중' : '임베딩 재생성 요청 등록'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void requestDocumentAction('hwp-conversion-intent')}
                        disabled={documentActionPendingAction !== null}
                        aria-busy={documentActionPendingAction === 'hwp-conversion-intent'}
                        className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs font-bold text-foreground hover:bg-secondary disabled:cursor-wait disabled:opacity-60"
                      >
                        {documentActionPendingAction === 'hwp-conversion-intent' ? (
                          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        ) : (
                          <FileText className="size-4" />
                        )}
                        {documentActionPendingAction === 'hwp-conversion-intent' ? '요청 등록 중' : 'HWP 변환 요청 등록'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setWebdavWriteConfirmationKey(currentWebdavWriteConfirmationKey)}
                        disabled={documentActionPendingAction !== null || !selectedWebdavAccount || selectedWorkspaceDocument.state_code !== 'ready'}
                        aria-busy={documentActionPendingAction === 'webdav-materialization-intent'}
                        className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-bold text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {documentActionPendingAction === 'webdav-materialization-intent' ? (
                          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        ) : (
                          <Server className="size-4" />
                        )}
                        {documentActionPendingAction === 'webdav-materialization-intent' ? 'WebDAV에 쓰는 중' : '고객 WebDAV에 문서 쓰기'}
                      </button>
                    </div>
                    {webdavWriteConfirmationKey === currentWebdavWriteConfirmationKey && documentActionPendingAction === null ? (
                      <div role="alertdialog" aria-modal="true" aria-labelledby="webdav-write-confirmation-title" aria-describedby="webdav-write-confirmation-description" className="mt-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-950">
                        <p id="webdav-write-confirmation-title" className="font-bold">고객 WebDAV에 문서를 쓰시겠습니까?</p>
                        <p id="webdav-write-confirmation-description" className="mt-1 text-sm leading-6">
                          {selectedWebdavAccountLabel}에 현재 문서를 기록합니다. 기존 파일이 있으면 충돌 조건을 확인하며, 이 작업은 고객 원본 저장소를 변경합니다.
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button type="button" onClick={() => setWebdavWriteConfirmationKey(null)} className="min-h-10 rounded-lg border border-border bg-background px-3 py-2 text-sm font-bold">취소</button>
                          <button
                            type="button"
                            onClick={() => {
                              setWebdavWriteConfirmationKey(null);
                              void requestDocumentAction('webdav-materialization-intent');
                            }}
                            className="min-h-10 rounded-lg bg-primary px-3 py-2 text-sm font-bold text-primary-foreground"
                          >WebDAV 쓰기 확인</button>
                        </div>
                      </div>
                    ) : null}
                    </>
                  )}
                  <dl className="mt-5 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                    <div>
                      <dt className="font-black text-muted-foreground">근거 상태</dt>
                      <dd className="mt-1 text-sm font-bold">{getAssetEvidenceLabel(selectedRepositoryAsset)}</dd>
                    </div>
                    <div>
                      <dt className="font-black text-muted-foreground">수집 시간</dt>
                      <dd className="mt-1 break-all text-sm font-bold">{formatDataTimestamp(selectedRepositoryAsset.captured_at)}</dd>
                    </div>
                    <div>
                      <dt className="font-black text-muted-foreground">본문 길이</dt>
                      <dd className="mt-1 text-sm font-bold">{formatCount(selectedRepositoryAsset.content_chars)}자</dd>
                    </div>
                    <div>
                      <dt className="font-black text-muted-foreground">쓰기 경계</dt>
                      <dd className="mt-1 text-sm font-bold">{getWriteBoundaryLabel(selectedRepositoryAsset.provider_write_executed)}</dd>
                    </div>
                    <div className="sm:col-span-2 lg:col-span-4">
                      <dt className="font-black text-muted-foreground">원본 근거</dt>
                      <dd className="mt-1 break-words text-sm font-semibold text-muted-foreground">
                        {toSafeReactText(selectedRepositoryAsset.detail_text)}
                      </dd>
                    </div>
                  </dl>
                </section>
              )}

              <section aria-label="WebDAV 반영 의도 승인" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-black text-primary">고객 원본 파일 반영</p>
                    <h2 className="mt-1 text-lg font-black">WebDAV 반영 의도 승인</h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                      첨부파일과 AI가 구조화한 산출물은 고객 WebDAV 원본에 반영할 의도로만 점검합니다.
                      실제 외부 쓰기는 원본 계정, If-Match 충돌 조건, 근거 확인을 통과한 뒤 별도 실행됩니다.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void requestWebdavWritebackIntent()}
                    disabled={isWritebackLoading || !canRequestWebdavWriteback}
                    aria-busy={isWebdavSourceLoading || isWritebackLoading}
                    className="inline-flex items-center justify-center gap-2 w-full whitespace-nowrap rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                  >
                    {isWritebackLoading && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
                    {isWritebackLoading ? '점검 중' : 'WebDAV 반영 의도 점검'}
                  </button>
                </div>

                <div role="status" aria-live="polite" className="mt-4 rounded-xl border border-border bg-background/70 p-4 text-sm">
                  {writebackStatus === 'idle' && (
                    <p className="text-muted-foreground">아직 WebDAV 외부 쓰기는 실행하지 않았습니다. 원본 선택과 충돌 조건만 확인합니다.</p>
                  )}
                  {writebackStatus === 'loading' && <p className="font-bold text-primary">WebDAV 반영 의도를 요청 중입니다.</p>}
                  {writebackStatus === 'idle' && webdavAccountStatus === 'error' && (
                    <p className="font-bold text-red-700">WebDAV 원본 계정 목록을 확인하지 못했습니다.</p>
                  )}
                  {writebackStatus === 'no_source' && (
                    <p className="font-bold text-amber-700">쓰기 가능한 고객 WebDAV 원본 계정이 없어 반영 의도를 만들 수 없습니다.</p>
                  )}
                  {writebackStatus === 'fetch_error' && (
                    <p className="font-bold text-red-700">WebDAV 원본 계정 목록을 확인하지 못해 반영 의도를 만들 수 없습니다.</p>
                  )}
                  {writebackStatus === 'conflict' && (
                    <p className="font-bold text-red-700">If-Match/ETag 충돌이 감지되어 고객 WebDAV 원본 파일을 덮어쓰지 않았습니다.</p>
                  )}
                  {writebackStatus === 'auth' && (
                    <p className="font-bold text-red-700">signed session이 필요합니다. 공개 identity header로는 WebDAV 반영 의도를 만들 수 없습니다.</p>
                  )}
                  {writebackStatus === 'error' && (
                    <p className="font-bold text-red-700">WebDAV 반영 의도 점검에 실패했습니다.</p>
                  )}
                  {writebackStatus === 'success' && writebackResult && (
                    <dl className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                      <div>
                        <dt className="font-black text-muted-foreground">반영 방식</dt>
                        <dd className="mt-1 text-sm font-bold text-foreground">{writebackResult.intent === 'writeback' ? '원본 반영 의도' : '의도 확인'}</dd>
                      </div>
                      <div>
                        <dt className="font-black text-muted-foreground">원본 선택</dt>
                        <dd className="mt-1 break-words text-sm font-bold text-foreground">{getWritebackTargetLabel(writebackResult, webdavAccountMap)}</dd>
                      </div>
                      <div>
                        <dt className="font-black text-muted-foreground">충돌 조건</dt>
                        <dd className="mt-1 text-sm font-bold text-foreground">{writebackResult.requires_if_match ? 'If-Match 필요' : '충돌 조건 없음'}</dd>
                      </div>
                      <div>
                        <dt className="font-black text-muted-foreground">근거</dt>
                        <dd className="mt-1 text-sm font-bold text-foreground">{writebackResult.provenance === 'server-authoritative' ? '서버 확인' : '근거 확인'}</dd>
                      </div>
                    </dl>
                  )}
                </div>
              </section>

              <section aria-label="중복 메일 canonical 스레드 의도" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-black text-primary">정확한 메일 중복 정리</p>
                    <h2 className="mt-1 text-lg font-black">중복 메일 스레드 정리 의도</h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                      ZIP 반입과 계정 간 포워딩으로 같은 메일이 다시 들어오면 Message-ID와 강한 본문 fingerprint로 기존 canonical 스레드에 연결할 의도를 만듭니다.
                      subject만 비슷한 메일은 자동 병합하지 않습니다.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void requestUniqueThreadIntent()}
                    disabled={isUniqueThreadLoading}
                    aria-busy={isUniqueThreadLoading}
                    className="inline-flex items-center justify-center gap-2 w-full whitespace-nowrap rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/90 disabled:cursor-wait disabled:opacity-60 sm:w-auto"
                  >
                    {isUniqueThreadLoading && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
                    {isUniqueThreadLoading ? '점검 중' : '중복 메일 스레드 의도 점검'}
                  </button>
                </div>

                <div role="status" aria-live="polite" className="mt-4 rounded-xl border border-border bg-background/70 p-4 text-sm">
                  {uniqueThreadStatus === 'idle' && (
                    <p className="text-muted-foreground">외부 쓰기나 DB 병합을 실행하지 않고 canonical 스레드 후보만 검증합니다.</p>
                  )}
                  {uniqueThreadStatus === 'loading' && <p className="font-bold text-primary">중복 메일 스레드 의도를 요청 중입니다.</p>}
                  {uniqueThreadStatus === 'auth' && (
                    <p className="font-bold text-red-700">signed session이 필요합니다. 공개 identity header로는 중복 메일 의도를 만들 수 없습니다.</p>
                  )}
                  {uniqueThreadStatus === 'error' && (
                    <p className="font-bold text-red-700">중복 메일 스레드 의도 점검에 실패했습니다.</p>
                  )}
                  {uniqueThreadStatus === 'success' && uniqueThreadResult && (
                    <div className="space-y-3">
                      <dl className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                        <div>
                          <dt className="font-black text-muted-foreground">검토 후보</dt>
                          <dd className="mt-1 font-mono text-sm text-foreground">{uniqueThreadResult.candidates_checked}</dd>
                        </div>
                        <div>
                          <dt className="font-black text-muted-foreground">중복 후보</dt>
                          <dd className="mt-1 font-mono text-sm text-foreground">{uniqueThreadResult.duplicates_found}</dd>
                        </div>
                        <div>
                          <dt className="font-black text-muted-foreground">쓰기 경계</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{getWriteBoundaryLabel(uniqueThreadResult.provider_write_executed)}</dd>
                        </div>
                        <div>
                          <dt className="font-black text-muted-foreground">감사 근거</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">기록됨</dd>
                        </div>
                      </dl>
                      <div className="grid gap-2">
                        {uniqueThreadResult.thread_updates.map((update: any) => (
                          <div key={(update as any).candidate_key} className="rounded-xl border border-border bg-card p-3 text-xs">
                            <p className="font-black text-foreground">{(update as any).match_reason === 'message_id' ? 'Message-ID 근거' : '본문 fingerprint 근거'}</p>
                            <p className="mt-1 text-muted-foreground">
                              기존 canonical 스레드에 연결할 후보입니다.
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </section>

              <div className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
                <div className="p-5 border-b border-border bg-secondary/30">
                  <h2 className="font-bold text-lg flex items-center gap-2"><FolderOpen className="size-5" /> AI 프로젝트 구조화된 첨부파일 (WebDAV)</h2>
                </div>
                <div className="p-4 grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
                  {projectFolders.length > 0 ? projectFolders.map(folder => (
                    <div key={folder.folder_uid} className="border border-border rounded-xl p-4 bg-background hover:bg-secondary/20 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
                      <div className="flex items-center gap-3 mb-2">
                        <FolderOpen className="size-5 text-primary" />
                        <span className="font-bold truncate">{toSafeReactText(folder.project_name)}</span>
                      </div>
                      <p className="mb-2 text-xs font-semibold text-primary">원본 폴더 연결됨</p>
                      <p className="text-xs text-muted-foreground">고객 WebDAV 경로 기준으로 연결된 프로젝트 폴더입니다.</p>
                    </div>
                  )) : (
                    <p className="text-sm text-muted-foreground col-span-full">AI가 구조화한 프로젝트 폴더가 없습니다.</p>
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
                <div className="p-5 border-b border-border bg-secondary/30">
                  <h2 className="font-bold text-lg">최근 수집/커넥터 근거</h2>
                </div>
                <div className="divide-y divide-border">
                  {dataSurfaceStatus === 'loading' && (
                    <div className="p-4 text-sm font-semibold text-muted-foreground">signed 데이터 품질 근거를 확인하는 중입니다.</div>
                  )}
                  {dataSurfaceStatus === 'error' && (
                    <div className="p-4 text-sm font-bold text-red-700">데이터 품질 표면을 확인하지 못했습니다.</div>
                  )}
                  {dataSurfaceStatus === 'ready' && connectorEvents.length === 0 && (
                    <div className="p-4 text-sm text-muted-foreground">이 워크스페이스에 기록된 커넥터 근거가 아직 없습니다.</div>
                  )}
                  {connectorEvents.map((event) => (
                    <div key={event.event_uid} className="p-4 flex flex-col gap-3 hover:bg-secondary/10 transition-colors sm:flex-row sm:items-center sm:justify-between focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
                      <div className="flex min-w-0 items-center gap-4">
                        <div className="p-2 rounded-lg bg-blue-100 text-blue-700"><RefreshCw className="size-4" /></div>
                        <div>
                          <p className="break-all font-bold text-sm">{toSafeReactText(event.signal_key)}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{toSafeReactText(event.detail_text ?? event.signal_key)}</p>
                        </div>
                      </div>
                      <div className="text-left sm:text-right">
                        <span className="text-xs font-bold px-2 py-1 rounded-full bg-blue-100 text-blue-700">{event.state_code}</span>
                        <p className="text-xs text-muted-foreground mt-1">{event.observed_at}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
  );
}
