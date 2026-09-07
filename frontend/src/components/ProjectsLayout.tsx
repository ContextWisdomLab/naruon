"use client";

import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, CheckCircle2, Clock, FileText, FolderOpen, GitBranch, ListChecks, Network, Search, User } from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { toSafeReactText } from '@/lib/safe-text';
import {
  buildAutomationBrief,
  buildProjectControlReadinessLayer,
  buildProjectReportDraftLayer,
  groupProjectTraceObjects,
  type ProjectCitation,
  type ProjectTraceObject,
} from './project-trace-readiness';

type ProjectViewMode = '프로젝트 상세' | '마일스톤' | '의사결정 로그';
type TaskStatus = 'open' | 'in_progress' | 'blocked' | 'done';
type TaskPriority = 'low' | 'normal' | 'high' | 'urgent';
type ProjectEvidenceSource = 'webdav_folder' | 'thread' | 'document';

interface ProjectFolder {
  folder_uid: string;
  project_name: string;
  webdav_path: string;
  owner_user_id: string;
  organization_id: string | null;
}

interface TicketTask {
  id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  source_type: string;
  source_email_id: string | null;
  related_thread_id: string | null;
  created_at: string;
  updated_at: string;
}

interface ProjectCandidate {
  candidate_uid: string;
  project_uid: string;
  title: string;
  status_code: string;
  score: number;
  object_count: number;
  requirement_count: number;
  issue_count: number;
  milestone_count: number;
  deliverable_count: number;
  participant_count: number;
  source_segment_count: number;
  representative_object_uids: string[];
  citation_bundle: ProjectCitation[];
  updated_at: string | null;
}

interface ProjectCandidateListResponse {
  candidates: ProjectCandidate[];
}

interface ProjectTraceEdge {
  edge_uid: string;
  source_uid: string;
  target_uid: string;
  edge_type: string;
  confidence: number;
  source_segment_uids: string[];
  citation_bundle: ProjectCitation[];
}

interface ProjectTraceability {
  project_uid: string;
  candidate: ProjectCandidate;
  objects: ProjectTraceObject[];
  edges: ProjectTraceEdge[];
}

interface ProjectEvidence {
  project_uid: string;
  object_uid: string;
  object_type: string;
  title: string;
  summary: string;
  status_code: string;
  confidence: number;
  citation_bundle: ProjectCitation[];
}

interface ProjectCorrectionResponse {
  correction_uid: string;
  object_uid: string;
  correction_action: string;
  before_json: Record<string, unknown>;
  after_json: Record<string, unknown>;
  rationale: string | null;
  actor_user_id: string;
  source_segment_uids: string[];
  created_at: string;
}

interface ProjectSummary {
  id: string;
  title: string;
  status: '진행 중' | '대기 중' | '완료' | '검토 중' | '상태 확인 불가';
  progress: number | null;
  category: string;
  evidence: string;
  sourcePath: string | null;
}

interface ProjectAccessScope {
  userId: string | null;
  organizationId: string | null;
}

const projectStatusClass = {
  '완료': 'bg-emerald-100 text-emerald-700',
  '진행 중': 'bg-blue-100 text-blue-700',
  '검토 중': 'bg-violet-100 text-violet-700',
  '대기 중': 'bg-slate-100 text-slate-700',
  '상태 확인 불가': 'bg-slate-100 text-slate-700',
} satisfies Record<ProjectSummary['status'], string>;

const taskStatusLabel: Record<TaskStatus, string> = {
  open: '실행 항목',
  in_progress: '진행 중',
  blocked: '검토 필요',
  done: '완료',
};

const taskStatusClass: Record<TaskStatus, string> = {
  open: 'bg-slate-100 text-slate-700',
  in_progress: 'bg-blue-100 text-blue-700',
  blocked: 'bg-amber-100 text-amber-800',
  done: 'bg-emerald-100 text-emerald-700',
};

const priorityLabel: Record<TaskPriority, string> = {
  urgent: '긴급',
  high: '높음',
  normal: '보통',
  low: '낮음',
};

const projectEvidenceSourceOptions = [
  { value: 'webdav_folder', label: 'WebDAV 폴더', description: '고객 소유 저장소 경계 기준' },
  { value: 'thread', label: '스레드 근거', description: '메일 스레드 의사결정 기준' },
  { value: 'document', label: '문서 근거', description: '문서 저장소 승인 기록 기준' },
] satisfies { value: ProjectEvidenceSource; label: string; description: string }[];

function safeText(value: string | null | undefined, fallback = '') {
  return toSafeReactText(value, fallback).trim() || fallback;
}

function isSourceRecord(sourceValue: unknown): sourceValue is Record<string, unknown> {
  return sourceValue !== null && typeof sourceValue === 'object' && !Array.isArray(sourceValue);
}

function hasTextFields(sourceRecord: Record<string, unknown>, fieldNames: string[]) {
  return fieldNames.every((fieldName) => typeof sourceRecord[fieldName] === 'string');
}

function isNullableText(sourceValue: unknown) {
  return sourceValue === null || typeof sourceValue === 'string';
}

function isProjectFolder(sourceValue: unknown): sourceValue is ProjectFolder {
  return isSourceRecord(sourceValue)
    && hasTextFields(sourceValue, ['folder_uid', 'project_name', 'webdav_path', 'owner_user_id'])
    && isNullableText(sourceValue.organization_id);
}

function isProjectTask(sourceValue: unknown): sourceValue is TicketTask {
  return isSourceRecord(sourceValue)
    && hasTextFields(sourceValue, ['id', 'title', 'source_type', 'created_at', 'updated_at'])
    && typeof sourceValue.status === 'string' && ['open', 'in_progress', 'blocked', 'done'].includes(sourceValue.status)
    && typeof sourceValue.priority === 'string' && ['low', 'normal', 'high', 'urgent'].includes(sourceValue.priority)
    && isNullableText(sourceValue.source_email_id)
    && isNullableText(sourceValue.related_thread_id);
}

function isProjectCandidate(sourceValue: unknown): sourceValue is ProjectCandidate {
  return isSourceRecord(sourceValue)
    && hasTextFields(sourceValue, ['candidate_uid', 'project_uid', 'title', 'status_code'])
    && typeof sourceValue.score === 'number' && Number.isFinite(sourceValue.score)
    && sourceValue.score >= 0 && sourceValue.score <= 1
    && ['object_count', 'requirement_count', 'issue_count', 'milestone_count', 'deliverable_count', 'participant_count', 'source_segment_count'].every((fieldName) => {
      const fieldValue = sourceValue[fieldName];
      return typeof fieldValue === 'number' && Number.isSafeInteger(fieldValue) && fieldValue >= 0;
    })
    && Array.isArray(sourceValue.representative_object_uids)
    && sourceValue.representative_object_uids.every((objectUid) => typeof objectUid === 'string')
    && Array.isArray(sourceValue.citation_bundle)
    && sourceValue.citation_bundle.every((citationValue) => isSourceRecord(citationValue)
      && hasTextFields(citationValue, ['content_segment_uid', 'source_kind', 'source_record_uid', 'safe_text_excerpt'])
      && isNullableText(citationValue.heading_path) && isNullableText(citationValue.segment_path)
      && typeof citationValue.ordinal_index === 'number' && Number.isSafeInteger(citationValue.ordinal_index))
    && isNullableText(sourceValue.updated_at);
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '날짜 미정';
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(date);
}

function buildProgress(tasks: TicketTask[]) {
  if (tasks.length === 0) return null;
  return Math.round((tasks.filter((task) => task.status === 'done').length / tasks.length) * 100);
}

function buildProjectStatus(tasks: TicketTask[]): ProjectSummary['status'] {
  if (tasks.some((task) => task.status === 'blocked')) return '검토 중';
  if (tasks.some((task) => task.status === 'in_progress')) return '진행 중';
  if (tasks.length > 0 && tasks.every((task) => task.status === 'done')) return '완료';
  return '대기 중';
}

function getProjectEvidenceLabel(evidence: string) {
  if (evidence === 'project_graph') return '문단 KG 근거';
  if (evidence === 'project_folders') return 'WebDAV 폴더 근거';
  if (evidence === 'ticket_tasks') return '작업 근거';
  return '원본 근거';
}

function getProjectBoundaryLabel(project: ProjectSummary) {
  if (project.evidence === 'project_graph') return '문단 citation 경계 확인됨';
  return project.sourcePath ? '저장소 경계 확인됨' : '작업 대기열 기준';
}

function getTaskSourceLabel(sourceType: string) {
  switch (sourceType) {
    case 'email':
      return '메일 근거';
    case 'webdav':
      return '문서 근거';
    case 'reply_sla':
      return '답장 대기';
    case 'self_sent_knowledge':
      return '자기참조 메일';
    default:
      return '원본 근거';
  }
}

function getTaskEvidenceLabel(task: TicketTask) {
  if (task.related_thread_id) return '스레드 근거 연결됨';
  if (task.source_email_id) return '메일 근거 연결됨';
  return '원본 연결 대기';
}

function getWorkspaceScopeLabel(scope: ProjectAccessScope) {
  return scope.organizationId ? '서명된 조직 워크스페이스' : '서명된 개인 워크스페이스';
}

function isAuthorizedToViewProject(folder: ProjectFolder, scope: ProjectAccessScope) {
  const ownerUserId = safeText(folder.owner_user_id);
  if (!ownerUserId || !scope.userId || ownerUserId !== scope.userId) return false;
  return (folder.organization_id ?? null) === scope.organizationId;
}

function buildProjects(folders: ProjectFolder[], tasks: TicketTask[]): ProjectSummary[] {
  const folderProjects: ProjectSummary[] = folders.map((folder) => ({
    id: folder.folder_uid,
    title: safeText(folder.project_name, '이름 없는 프로젝트'),
    status: '상태 확인 불가',
    progress: null,
    category: 'WebDAV 프로젝트',
    evidence: 'project_folders',
    sourcePath: safeText(folder.webdav_path, ''),
  }));

  if (folderProjects.length > 0) return folderProjects;

  return [
    {
      id: 'workspace_task_backlog',
      title: '원본 연결 작업 대기열',
      status: tasks.length ? buildProjectStatus(tasks) : '상태 확인 불가',
      progress: buildProgress(tasks),
      category: '작업 대기열',
      evidence: 'ticket_tasks',
      sourcePath: null,
    },
  ];
}

function countByStatus(tasks: TicketTask[], status: TaskStatus) {
  return tasks.filter((task) => task.status === status).length;
}

function semanticStatusToProjectStatus(statusCode: string): ProjectSummary['status'] {
  if (statusCode === 'approved' || statusCode === 'confirmed') return '진행 중';
  if (statusCode === 'needs_review') return '검토 중';
  return '대기 중';
}

function buildSemanticProjects(candidates: ProjectCandidate[]): ProjectSummary[] {
  return candidates.map((candidate) => ({
    id: candidate.project_uid,
    title: safeText(candidate.title, '이름 없는 프로젝트 후보'),
    status: semanticStatusToProjectStatus(candidate.status_code),
    progress: null,
    category: 'Semantic KG 프로젝트',
    evidence: 'project_graph',
    sourcePath: null,
  }));
}

function objectTypeLabel(objectType: string) {
  switch (objectType) {
    case 'project_candidate':
      return '프로젝트 후보';
    case 'requirement':
      return '요구사항';
    case 'feature':
      return '기능정의';
    case 'issue':
      return '이슈';
    case 'milestone':
      return '일정';
    case 'wbs_item':
      return 'WBS';
    case 'deliverable':
      return '산출물';
    case 'participant':
      return '인물';
    case 'data_requirement':
      return '데이터 요건';
    case 'erd_candidate':
      return 'ERD 후보';
    case 'infra_requirement':
      return '인프라 요건';
    case 'report_delta':
      return '보고 변화';
    case 'wiki_projection':
      return '위키 투영';
    default:
      return '프로젝트 객체';
  }
}

function citationSourceLabel(citation: ProjectCitation) {
  if (citation.segment_path) return citation.segment_path;
  if (citation.heading_path) return citation.heading_path;
  return citation.source_kind;
}

export function ProjectsLayout() {
  const [folders, setFolders] = useState<ProjectFolder[]>([]);
  const [tasks, setTasks] = useState<TicketTask[]>([]);
  const [semanticCandidates, setSemanticCandidates] = useState<ProjectCandidate[]>([]);
  const [traceability, setTraceability] = useState<ProjectTraceability | null>(null);
  const [traceFailureProjectUid, setTraceFailureProjectUid] = useState<string | null>(null);
  const [selectedObjectUid, setSelectedObjectUid] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<ProjectEvidence | null>(null);
  const [evidenceFailureKey, setEvidenceFailureKey] = useState<string | null>(null);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [lastConfirmedCandidateUid, setLastConfirmedCandidateUid] = useState<string | null>(null);
  const [correctionSubmitting, setCorrectionSubmitting] = useState(false);
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const [lastCorrection, setLastCorrection] = useState<ProjectCorrectionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [sourceRetryRevision, setSourceRetryRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ProjectViewMode>('프로젝트 상세');
  const [projectScope, setProjectScope] = useState<ProjectAccessScope>({
    userId: null,
    organizationId: null,
  });
  const [evidenceDraft, setEvidenceDraft] = useState('WebDAV 프로젝트 폴더를 작업 경계로 사용합니다.');
  const [evidenceSource, setEvidenceSource] = useState<ProjectEvidenceSource>('webdav_folder');

  useEffect(() => {
    let cancelled = false;

    void Promise.all([
      apiClient.get<ProjectFolder[]>('/api/webdav/folders'),
      apiClient.get<TicketTask[]>('/api/tasks'),
      apiClient.get<ProjectCandidateListResponse>('/api/projects/candidates'),
      apiClient.getServerSessionClaims(),
    ])
      .then(([folderRows, taskRows, candidateRows, claims]) => {
        if (cancelled) return;
        if (!claims.userId) throw new Error('Project session unavailable');
        if (!Array.isArray(folderRows) || !folderRows.every(isProjectFolder)
          || !Array.isArray(taskRows) || !taskRows.every(isProjectTask)
          || !isSourceRecord(candidateRows) || !Array.isArray(candidateRows.candidates)
          || !candidateRows.candidates.every(isProjectCandidate)) {
          throw new Error('Project source response invalid');
        }
        setFolders(folderRows);
        setTasks(taskRows);
        setSemanticCandidates(candidateRows.candidates);
        setProjectScope({
          userId: claims.userId,
          organizationId: claims.organizationId,
        });
        setError(null);
      })
      .catch((fetchError: Error) => {
        if (cancelled) return;
        setFolders([]);
        setTasks([]);
        setSemanticCandidates([]);
        setError(fetchError.message ? '프로젝트 근거를 불러오지 못했습니다. 데이터 연결 상태를 확인해 주세요.' : '프로젝트 근거를 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sourceRetryRevision]);

  const authorizedFolders = useMemo(
    () => folders.filter((folder) => isAuthorizedToViewProject(folder, projectScope)),
    [folders, projectScope],
  );
  const projects = useMemo(() => {
    const semanticProjects = buildSemanticProjects(semanticCandidates);
    return semanticProjects.length > 0 ? semanticProjects : buildProjects(authorizedFolders, tasks);
  }, [authorizedFolders, semanticCandidates, tasks]);
  const activeProject = projects.find((project) => project.id === selectedProjectId) ?? projects[0];
  const activeSemanticCandidate = semanticCandidates.find((candidate) => candidate.project_uid === activeProject.id) ?? null;
  const loadedTasks = tasks;
  const openCount = countByStatus(loadedTasks, 'open');
  const inProgressCount = countByStatus(loadedTasks, 'in_progress');
  const blockedCount = countByStatus(loadedTasks, 'blocked');
  const doneCount = countByStatus(loadedTasks, 'done');
  const sourceTypeCount = new Set(loadedTasks.map((task) => task.source_type)).size;
  const projectEvidenceLabel = getProjectEvidenceLabel(activeProject.evidence);
  const projectBoundaryLabel = getProjectBoundaryLabel(activeProject);
  const workspaceScopeLabel = getWorkspaceScopeLabel(projectScope);
  const selectedEvidenceOption = projectEvidenceSourceOptions.find((option) => option.value === evidenceSource) ?? projectEvidenceSourceOptions[0];
  const evidenceDraftPreview = safeText(evidenceDraft, '근거 메모 없음');
  const currentTraceability = traceability?.project_uid === activeSemanticCandidate?.project_uid ? traceability : null;
  const currentObjects = useMemo(() => currentTraceability?.objects ?? [], [currentTraceability?.objects]);
  const groupedObjects = useMemo(() => groupProjectTraceObjects(currentObjects), [currentObjects]);
  const automationBrief = useMemo(() => buildAutomationBrief(groupedObjects), [groupedObjects]);
  const reportDraftLayer = useMemo(() => buildProjectReportDraftLayer(groupedObjects), [groupedObjects]);
  const controlReadinessLayer = useMemo(() => buildProjectControlReadinessLayer(groupedObjects), [groupedObjects]);
  const traceLoading = Boolean(activeSemanticCandidate && !currentTraceability && traceFailureProjectUid !== activeSemanticCandidate.project_uid);
  const selectedTraceObject = currentTraceability?.objects.find((item) => item.object_uid === selectedObjectUid) ?? currentTraceability?.objects[0] ?? null;
  const selectedEvidenceProjectUid = activeSemanticCandidate?.project_uid ?? null;
  // ⚡ Bolt: Memoize project tasks list to prevent O(N) array mapping overhead
  const loadedTasksList = useMemo(() => (
    <ol className="divide-y divide-border">
      {loadedTasks.slice(0, 8).map((task) => (
        <li key={task.id} className="grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${taskStatusClass[task.status]}`}>{taskStatusLabel[task.status]}</span>
              <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-bold text-muted-foreground">{priorityLabel[task.priority]}</span>
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">{getTaskSourceLabel(task.source_type)}</span>
            </div>
            <h3 className="mt-2 break-keep font-bold text-sm">{safeText(task.title, '제목 없는 작업')}</h3>
            <p className="mt-1 text-xs font-semibold text-muted-foreground">{getTaskEvidenceLabel(task)}</p>
          </div>
          <time className="flex items-center gap-1 text-xs text-muted-foreground sm:justify-end"><Clock className="size-3" />{formatDate(task.updated_at)}</time>
        </li>
      ))}
    </ol>
  ), [loadedTasks]);

  const selectedEvidenceObjectUid = selectedTraceObject?.object_uid ?? null;
  const selectedEvidenceKey = selectedEvidenceProjectUid && selectedEvidenceObjectUid ? `${selectedEvidenceProjectUid}:${selectedEvidenceObjectUid}` : null;
  const currentEvidence = selectedEvidenceKey && selectedEvidence && `${selectedEvidence.project_uid}:${selectedEvidence.object_uid}` === selectedEvidenceKey ? selectedEvidence : null;
  const evidenceLoading = Boolean(selectedEvidenceKey && !currentEvidence && evidenceFailureKey !== selectedEvidenceKey);
  const evidenceCitations = currentEvidence?.citation_bundle ?? selectedTraceObject?.citation_bundle ?? [];
  const currentCorrection = selectedTraceObject && lastCorrection?.object_uid === selectedTraceObject.object_uid ? lastCorrection : null;
  const candidateConfirmed = activeSemanticCandidate ? activeSemanticCandidate.status_code === 'confirmed' || lastConfirmedCandidateUid === activeSemanticCandidate.candidate_uid : false;

  useEffect(() => {
    if (!activeSemanticCandidate) {
      return;
    }
    let cancelled = false;
    const projectUid = activeSemanticCandidate.project_uid;
    void apiClient.get<ProjectTraceability>(`/api/projects/${encodeURIComponent(activeSemanticCandidate.project_uid)}/traceability`)
      .then((response) => {
        if (cancelled) return;
        setTraceability(response);
        setTraceFailureProjectUid(null);
        setSelectedObjectUid(response.objects[0]?.object_uid ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setTraceability(null);
        setTraceFailureProjectUid(projectUid);
        setSelectedObjectUid(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeSemanticCandidate]);

  useEffect(() => {
    if (!selectedEvidenceProjectUid || !selectedEvidenceObjectUid || !selectedEvidenceKey) {
      return;
    }
    let cancelled = false;
    const projectUid = selectedEvidenceProjectUid;
    const objectUid = selectedEvidenceObjectUid;
    const evidenceKey = selectedEvidenceKey;
    void apiClient.get<ProjectEvidence>(
      `/api/projects/${encodeURIComponent(projectUid)}/evidence/${encodeURIComponent(objectUid)}`,
    )
      .then((response) => {
        if (cancelled) return;
        setSelectedEvidence(response);
        setEvidenceFailureKey((current) => (current === evidenceKey ? null : current));
      })
      .catch(() => {
        if (cancelled) return;
        setEvidenceFailureKey(evidenceKey);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedEvidenceKey, selectedEvidenceObjectUid, selectedEvidenceProjectUid]);

  async function handleConfirmCandidate() {
    if (!activeSemanticCandidate || confirmSubmitting) return;
    setConfirmSubmitting(true);
    setConfirmError(null);
    try {
      const confirmedCandidate = await apiClient.post<ProjectCandidate>(
        `/api/projects/candidates/${encodeURIComponent(activeSemanticCandidate.candidate_uid)}/confirm`,
        {},
      );
      setSemanticCandidates((candidates) => candidates.map((candidate) => (
        candidate.candidate_uid === confirmedCandidate.candidate_uid ? confirmedCandidate : candidate
      )));
      setTraceability((current) => (
        current?.project_uid === confirmedCandidate.project_uid ? { ...current, candidate: confirmedCandidate } : current
      ));
      setLastConfirmedCandidateUid(confirmedCandidate.candidate_uid);
    } catch {
      setConfirmError('프로젝트 후보 확정을 저장하지 못했습니다.');
    } finally {
      setConfirmSubmitting(false);
    }
  }

  async function handleMarkEvidenceReviewed() {
    if (!activeSemanticCandidate || !selectedTraceObject || correctionSubmitting) return;
    setCorrectionSubmitting(true);
    setCorrectionError(null);
    const projectUid = activeSemanticCandidate.project_uid;
    const objectUid = selectedTraceObject.object_uid;
    const sourceSegmentUids = evidenceCitations.length > 0
      ? evidenceCitations.map((citation) => citation.content_segment_uid)
      : selectedTraceObject.source_segment_uids;
    try {
      const correction = await apiClient.post<ProjectCorrectionResponse>(
        `/api/projects/${encodeURIComponent(projectUid)}/corrections`,
        {
          object_uid: objectUid,
          correction_action: 'mark_evidence_reviewed',
          after_json: {
            status_code: 'approved',
            title: selectedTraceObject.title,
            evidence_review_state: 'reviewed',
            reviewed_at: new Date().toISOString(),
          },
          rationale: 'Reviewed from the Project Command Center Evidence Inspector.',
          source_segment_uids: sourceSegmentUids,
        },
      );
      const nextStatus = typeof correction.after_json.status_code === 'string' ? correction.after_json.status_code : null;
      const nextTitle = typeof correction.after_json.title === 'string' ? correction.after_json.title : null;
      setLastCorrection(correction);
      setTraceability((current) => {
        if (!current || current.project_uid !== projectUid) return current;
        return {
          ...current,
          objects: current.objects.map((projectObject) => (
            projectObject.object_uid === objectUid
              ? {
                  ...projectObject,
                  status_code: nextStatus ?? projectObject.status_code,
                  title: nextTitle ?? projectObject.title,
                }
              : projectObject
          )),
        };
      });
      setSelectedEvidence((current) => {
        if (!current || current.project_uid !== projectUid || current.object_uid !== objectUid) return current;
        return {
          ...current,
          status_code: nextStatus ?? current.status_code,
          title: nextTitle ?? current.title,
        };
      });
    } catch {
      setCorrectionError('문단 근거 검토 결과를 저장하지 못했습니다.');
    } finally {
      setCorrectionSubmitting(false);
    }
  }

  if (loading || error) {
    return (
      <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto bg-background p-4 text-foreground md:p-6">
        <h1 className="text-xl font-bold">프로젝트 워크스페이스</h1>
        <p role={loading ? 'status' : 'alert'} className="break-keep rounded-lg border border-border bg-card p-4">
          {loading ? '프로젝트 근거를 불러오는 중입니다.' : error}
        </p>
        {!loading && (
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => {
              setLoading(true);
              setError(null);
              setSourceRetryRevision((currentRevision) => currentRevision + 1);
            }} className="min-h-10 rounded-md bg-primary px-4 font-semibold text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">다시 불러오기</button>
            <a href="/data" className="flex min-h-10 items-center rounded-md border border-border px-4 font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">원본 연결</a>
          </div>
        )}
      </main>
    );
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 overflow-x-hidden bg-background text-foreground">
      <aside className="hidden w-72 shrink-0 flex-col overflow-y-auto border-r border-border bg-card lg:flex">
        <div className="border-b border-border p-4">
          <a href="/data" className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-bold text-primary-foreground shadow-sm hover:bg-primary/90">
            <FolderOpen className="size-4" /> 새 프로젝트
          </a>
          <div className="relative mt-4">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <a href="/search" aria-label="프로젝트 관련 문서와 메일 연결" className="flex h-9 w-full items-center rounded-md border border-border bg-background pl-9 pr-4 text-sm font-semibold text-muted-foreground hover:bg-secondary">
              관련 문서/메일 연결
            </a>
          </div>
        </div>

        <div className="flex-1 space-y-1 p-3">
          {projects.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => setSelectedProjectId(project.id)}
              className={`w-full rounded-lg border px-3 py-3 text-left transition-colors ${activeProject.id === project.id ? 'border-primary/30 bg-secondary' : 'border-transparent hover:bg-secondary/50'}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-bold text-muted-foreground">{project.category}</span>
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${projectStatusClass[project.status]}`}>{project.status}</span>
              </div>
              <h3 className="mt-1 line-clamp-2 font-bold text-sm text-foreground">{project.title}</h3>
              <div className="mt-3 flex items-center gap-2">
                {project.progress === null ? (
                  <span className="text-xs font-semibold text-muted-foreground">진행률 확인 불가</span>
                ) : (
                  <>
                    <progress aria-label="조회된 작업 완료율" className="h-1.5 min-w-0 flex-1" max={100} value={project.progress} />
                    <span className="text-xs font-semibold text-muted-foreground">{project.progress}%</span>
                  </>
                )}
              </div>
            </button>
          ))}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-background">
        <header className="flex shrink-0 flex-col gap-3 border-b border-border bg-card px-4 py-4 lg:h-24 lg:flex-row lg:items-center lg:justify-between lg:px-6">
          <div className="min-w-0">
            <h1 className="break-keep text-sm font-black text-foreground lg:text-base">프로젝트 워크스페이스</h1>
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs font-bold text-muted-foreground">
              <span>{activeProject.category}</span>
              <span>/</span>
              <span>{projectEvidenceLabel}</span>
            </div>
            <h2 className="break-keep text-xl font-bold leading-tight lg:text-2xl">{activeProject.title}</h2>
          </div>
          <div className="flex min-w-0 flex-col gap-3 lg:items-end">
            <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
              {projects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  onClick={() => setSelectedProjectId(project.id)}
                  className={`min-h-10 shrink-0 rounded-xl px-3 text-xs font-bold ${activeProject.id === project.id ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground'}`}
                >
                  {project.title}
                </button>
              ))}
            </div>
            <div className="flex overflow-x-auto rounded-md border border-border">
              {(['프로젝트 상세', '마일스톤', '의사결정 로그'] as ProjectViewMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setViewMode(mode)}
                  className={`min-h-9 shrink-0 px-3 text-xs font-semibold transition-colors sm:px-4 sm:text-sm ${viewMode === mode ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-secondary'}`}
                >
                  {mode}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <a href="/tasks" className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-semibold hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">작업 보드</a>
              <a href="/data" className="rounded-md bg-primary px-4 py-1.5 text-sm font-bold text-primary-foreground hover:bg-primary/90">원본 연결</a>
            </div>
          </div>
        </header>

        <div role="region" aria-label="프로젝트 내용" className="grid flex-1 gap-6 overflow-y-auto p-4 md:p-6 lg:grid-cols-3">
          <div className="min-w-0 space-y-6 lg:col-span-2">
            {activeSemanticCandidate ? (
              <section aria-label="프로젝트 관계 맥락 상태" className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
                <div className="flex flex-col gap-3 border-b border-border p-5 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0">
                    <h2 className="flex items-center gap-2 font-bold text-lg"><Network className="size-5 text-primary" /> 프로젝트 관계 맥락</h2>
                    <p className="mt-1 text-sm font-semibold text-muted-foreground">모든 항목은 문단 citation bundle을 기준으로 표시됩니다.</p>
                  </div>
                  <div className="flex min-w-0 flex-col gap-2 md:items-end">
                    <div className="grid min-w-44 grid-cols-2 gap-2 text-center">
                      <div className="rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-xs font-bold text-muted-foreground">근거 문단</p>
                        <p className="font-mono text-lg font-black">{activeSemanticCandidate.source_segment_count}</p>
                      </div>
                      <div className="rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-xs font-bold text-muted-foreground">관계 맥락 객체</p>
                        <p className="font-mono text-lg font-black">{activeSemanticCandidate.object_count}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                      <span className="rounded-full bg-secondary px-2.5 py-1 text-muted-foreground">Sales KPI: evidence-ready</span>
                      <button
                        type="button"
                        onClick={handleConfirmCandidate}
                        disabled={confirmSubmitting || candidateConfirmed}
                        aria-busy={confirmSubmitting}
                        className="rounded-md bg-primary px-3 py-1.5 text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:bg-secondary disabled:text-muted-foreground"
                      >
                        {candidateConfirmed ? '프로젝트 후보 확정됨' : confirmSubmitting ? '확정 저장 중' : '프로젝트 후보 확정'}
                      </button>
                    </div>
                    {confirmError ? <p role="alert" className="text-xs font-semibold text-destructive">{confirmError}</p> : null}
                  </div>
                </div>
                <div className="grid gap-4 p-5 md:grid-cols-5">
                  {[
                    { label: '요구사항', value: activeSemanticCandidate.requirement_count },
                    { label: '이슈', value: activeSemanticCandidate.issue_count },
                    { label: '일정', value: activeSemanticCandidate.milestone_count },
                    { label: '산출물', value: activeSemanticCandidate.deliverable_count },
                    { label: '인물', value: activeSemanticCandidate.participant_count },
                  ].map((item) => (
                    <div key={item.label} className="rounded-lg border border-border bg-background p-3">
                      <p className="text-xs font-bold text-muted-foreground">{item.label}</p>
                      <p className="mt-2 font-mono text-xl font-black">{item.value}</p>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {activeSemanticCandidate ? (
              <section aria-label="프로젝트 자동화 브리프" className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
                <div className="flex flex-col gap-3 border-b border-border p-5 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0">
                    <h2 className="flex items-center gap-2 font-bold text-lg"><ListChecks className="size-5 text-primary" /> 자동화 브리프</h2>
                    <p className="mt-1 text-sm font-semibold text-muted-foreground">Traceability 객체를 WBS, 보고, 위키, 데이터 산출물로 접어 보여줍니다.</p>
                  </div>
                  <div className="grid min-w-52 grid-cols-3 gap-2 text-center">
                    {automationBrief.metrics.map((metric) => (
                      <div key={metric.key} className="rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-[11px] font-bold text-muted-foreground">{metric.label}</p>
                        <p className="mt-1 font-mono text-lg font-black">{metric.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
                {currentTraceability ? (
                  <div className="p-5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">
                        {automationBrief.readyDomainCount} / {automationBrief.totalDomainCount} domains ready
                      </span>
                      <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-bold text-muted-foreground">Buyer KPI: source-backed delivery automation</span>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {automationBrief.domains.map((domain) => (
                        <article key={domain.key} className="rounded-lg border border-border bg-background p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h3 className="break-keep text-sm font-black">{domain.label}</h3>
                              <p className="mt-1 text-xs leading-5 text-muted-foreground">{domain.description}</p>
                            </div>
                            <span className={`shrink-0 rounded px-2 py-1 text-xs font-bold ${domain.count > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                              {domain.count > 0 ? '근거 있음' : '대기'}
                            </span>
                          </div>
                          <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                            <div className="rounded-md border border-border bg-card p-2">
                              <dt className="font-bold text-muted-foreground">객체</dt>
                              <dd className="mt-1 font-mono text-base font-black">{domain.count}</dd>
                            </div>
                            <div className="rounded-md border border-border bg-card p-2">
                              <dt className="font-bold text-muted-foreground">문단 근거</dt>
                              <dd className="mt-1 font-mono text-base font-black">{domain.citationCount}</dd>
                            </div>
                          </dl>
                          <p className="mt-3 line-clamp-2 text-xs font-semibold text-foreground">{domain.primaryTitle}</p>
                        </article>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="p-5">
                    <p className="rounded-xl border border-dashed border-border p-4 text-sm font-semibold text-muted-foreground">
                      {traceLoading ? '자동화 브리프를 구성하는 중입니다.' : '자동화 브리프를 구성할 traceability 근거가 없습니다.'}
                    </p>
                  </div>
                )}
              </section>
            ) : null}

            {activeSemanticCandidate ? (
              <section aria-label="프로젝트 보고 초안" className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
                <div className="flex flex-col gap-3 border-b border-border p-5 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0">
                    <h2 className="flex items-center gap-2 font-bold text-lg"><FileText className="size-5 text-primary" /> 보고 초안</h2>
                    <p className="mt-1 text-sm font-semibold text-muted-foreground">문단 근거가 있는 객체만 주간·일일 보고와 상태 업데이트 문구로 투영합니다.</p>
                  </div>
                  <div className="grid min-w-52 grid-cols-3 gap-2 text-center">
                    {reportDraftLayer.metrics.map((metric) => (
                      <div key={metric.key} className="rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-[11px] font-bold text-muted-foreground">{metric.label}</p>
                        <p className="mt-1 font-mono text-lg font-black">{metric.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
                {currentTraceability ? (
                  <div className="p-5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">
                        {reportDraftLayer.readyDraftCount} / {reportDraftLayer.totalDraftCount} drafts ready
                      </span>
                      <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-bold text-muted-foreground">Reviewer KPI: report-ready status update</span>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {reportDraftLayer.drafts.map((draft) => (
                        <article key={draft.key} className="rounded-lg border border-border bg-background p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h3 className="break-keep text-sm font-black">{draft.label}</h3>
                              <p className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">{draft.summary}</p>
                            </div>
                            <span className={`shrink-0 rounded px-2 py-1 text-xs font-bold ${draft.sourceCount > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                              {draft.sourceCount > 0 ? '근거 있음' : '대기'}
                            </span>
                          </div>
                          <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                            <div className="rounded-md border border-border bg-card p-2">
                              <dt className="font-bold text-muted-foreground">보고 근거</dt>
                              <dd className="mt-1 font-mono text-base font-black">{draft.sourceCount}</dd>
                            </div>
                            <div className="rounded-md border border-border bg-card p-2">
                              <dt className="font-bold text-muted-foreground">문단 citation</dt>
                              <dd className="mt-1 font-mono text-base font-black">{draft.citationCount}</dd>
                            </div>
                          </dl>
                          <p className="mt-3 line-clamp-2 text-xs font-semibold text-foreground">{draft.sourceTitle}</p>
                        </article>
                      ))}
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-3">
                      {[reportDraftLayer.statusUpdate, reportDraftLayer.riskAction, reportDraftLayer.reviewerAction].map((item) => (
                        <p key={item} className="rounded-lg border border-border bg-background p-3 text-xs font-bold leading-5 text-foreground">{item}</p>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="p-5">
                    <p className="rounded-xl border border-dashed border-border p-4 text-sm font-semibold text-muted-foreground">
                      {traceLoading ? '보고 초안을 구성하는 중입니다.' : '보고 초안을 구성할 traceability 근거가 없습니다.'}
                    </p>
                  </div>
                )}
              </section>
            ) : null}

            {activeSemanticCandidate ? (
              <section aria-label="프로젝트 컨트롤 준비도" className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
                <div className="flex flex-col gap-3 border-b border-border p-5 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0">
                    <h2 className="flex items-center gap-2 font-bold text-lg"><CheckCircle2 className="size-5 text-primary" /> 컨트롤 준비도</h2>
                    <p className="mt-1 text-sm font-semibold text-muted-foreground">인수·일정·범위·데이터·액션 근거를 실사 가능한 컨트롤로 묶습니다.</p>
                  </div>
                  <div className="grid min-w-52 grid-cols-2 gap-2 text-center md:grid-cols-4">
                    {controlReadinessLayer.metrics.map((metric) => (
                      <div key={metric.key} className="rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-[11px] font-bold text-muted-foreground">{metric.label}</p>
                        <p className="mt-1 font-mono text-lg font-black">{metric.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
                {currentTraceability ? (
                  <div className="p-5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">
                        {controlReadinessLayer.readyItemCount} / {controlReadinessLayer.totalItemCount} controls ready
                      </span>
                      <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-bold text-muted-foreground">Diligence KPI: source-backed control readiness</span>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {controlReadinessLayer.items.map((item) => (
                        <article key={item.key} className="rounded-lg border border-border bg-background p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h3 className="break-keep text-sm font-black">{item.label}</h3>
                              <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.description}</p>
                            </div>
                            <span className={`shrink-0 rounded px-2 py-1 text-xs font-bold ${item.count > 0 && item.citationCount > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                              {item.count > 0 && item.citationCount > 0 ? '준비됨' : '근거 대기'}
                            </span>
                          </div>
                          <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                            <div className="rounded-md border border-border bg-card p-2">
                              <dt className="font-bold text-muted-foreground">컨트롤 근거</dt>
                              <dd className="mt-1 font-mono text-base font-black">{item.count}</dd>
                            </div>
                            <div className="rounded-md border border-border bg-card p-2">
                              <dt className="font-bold text-muted-foreground">문단 citation</dt>
                              <dd className="mt-1 font-mono text-base font-black">{item.citationCount}</dd>
                            </div>
                          </dl>
                          <p className="mt-3 line-clamp-2 text-xs font-semibold text-foreground">{item.primaryTitle}</p>
                        </article>
                      ))}
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      {[controlReadinessLayer.summary, controlReadinessLayer.reviewerAction].map((item) => (
                        <p key={item} className="rounded-lg border border-border bg-background p-3 text-xs font-bold leading-5 text-foreground">{item}</p>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="p-5">
                    <p className="rounded-xl border border-dashed border-border p-4 text-sm font-semibold text-muted-foreground">
                      {traceLoading ? '컨트롤 준비도를 구성하는 중입니다.' : '컨트롤 준비도를 구성할 traceability 근거가 없습니다.'}
                    </p>
                  </div>
                )}
              </section>
            ) : null}

            {activeSemanticCandidate ? (
              <section aria-label="프로젝트 추적성 맵" className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
                <div className="flex items-center justify-between border-b border-border p-5">
                  <h2 className="flex items-center gap-2 font-bold text-lg"><GitBranch className="size-5 text-primary" /> Traceability Map</h2>
                  <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-bold text-muted-foreground">
                    {traceLoading ? '동기화 중' : `${currentTraceability?.edges.length ?? 0} edges`}
                  </span>
                </div>
                {currentTraceability ? (
                  <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
                    <div className="min-w-0 divide-y divide-border">
                      {currentTraceability.objects.slice(0, 10).map((projectObject) => (
                        <button
                          key={projectObject.object_uid}
                          type="button"
                          onClick={() => setSelectedObjectUid(projectObject.object_uid)}
                          className={`grid w-full gap-2 px-5 py-4 text-left transition-colors hover:bg-secondary/50 ${selectedTraceObject?.object_uid === projectObject.object_uid ? 'bg-primary/5' : 'bg-card'}`}
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">{objectTypeLabel(projectObject.object_type)}</span>
                            <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-bold text-muted-foreground">{projectObject.citation_bundle.length} citations</span>
                            <span className="font-mono text-xs font-bold text-muted-foreground">{Math.round(projectObject.confidence * 100)}%</span>
                          </div>
                          <h3 className="line-clamp-2 break-keep text-sm font-bold">{safeText(projectObject.title, '제목 없는 관계 맥락 객체')}</h3>
                          <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{safeText(projectObject.summary, '종합 대기')}</p>
                        </button>
                      ))}
                    </div>
                    <aside aria-label="Evidence Inspector" className="min-w-0 border-t border-border bg-background p-5 lg:border-l lg:border-t-0">
                      <h3 className="flex items-center gap-2 text-sm font-black"><FileText className="size-4 text-primary" /> Evidence Inspector</h3>
                      {selectedTraceObject ? (
                        <div className="mt-4 space-y-4">
                          <div>
                            <p className="text-xs font-bold text-muted-foreground">선택 객체</p>
                            <p className="mt-1 break-keep text-sm font-bold">{safeText(selectedTraceObject.title, '선택된 객체')}</p>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <div className="rounded-lg border border-border bg-card p-3">
                              <p className="text-xs font-bold text-muted-foreground">상태</p>
                              <p className="mt-1 inline-flex rounded bg-secondary px-2 py-1 text-xs font-bold">{currentEvidence?.status_code ?? selectedTraceObject.status_code}</p>
                            </div>
                            <div className="rounded-lg border border-border bg-card p-3">
                              <p className="text-xs font-bold text-muted-foreground">근거 신뢰도</p>
                              <p className="mt-1 font-mono text-sm font-black">{Math.round((currentEvidence?.confidence ?? selectedTraceObject.confidence) * 100)}%</p>
                            </div>
                          </div>
                          <div className="rounded-lg border border-border bg-card p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-xs font-bold text-muted-foreground">검토 루프</p>
                              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">
                                {currentEvidence ? 'Full evidence 확인됨' : evidenceLoading ? 'Full evidence 확인 중' : 'Trace citation 사용'}
                              </span>
                            </div>
                            <div className="mt-3 grid gap-2 text-xs font-semibold text-muted-foreground">
                              <p>Source coverage: {evidenceCitations.length} 문단</p>
                              <p>Review readiness: {currentCorrection ? 'correction trail 저장됨' : '검토 대기'}</p>
                            </div>
                            <button
                              type="button"
                              onClick={handleMarkEvidenceReviewed}
                              disabled={correctionSubmitting || evidenceLoading}
                              aria-busy={correctionSubmitting}
                              className="mt-3 min-h-9 w-full rounded-md bg-primary px-3 text-xs font-bold text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:bg-secondary disabled:text-muted-foreground"
                            >
                              {correctionSubmitting ? '검토 저장 중' : '문단 근거 검토 저장'}
                            </button>
                            {currentCorrection ? (
                              <p className="mt-2 text-xs font-semibold text-emerald-700">
                                Correction trail 저장됨 / {typeof currentCorrection.after_json.status_code === 'string' ? currentCorrection.after_json.status_code : 'status updated'} / {formatDate(currentCorrection.created_at)}
                              </p>
                            ) : null}
                            {correctionError ? <p role="alert" className="mt-2 text-xs font-semibold text-destructive">{correctionError}</p> : null}
                          </div>
                          <div>
                            <p className="text-xs font-bold text-muted-foreground">문단 근거</p>
                            <ol className="mt-2 space-y-2">
                              {evidenceCitations.slice(0, 3).map((citation) => (
                                <li key={citation.content_segment_uid} className="rounded-lg border border-border bg-card p-3">
                                  <p className="font-mono text-[11px] font-bold text-primary">{citationSourceLabel(citation)}</p>
                                  <p className="mt-2 line-clamp-4 text-xs leading-5 text-foreground">{safeText(citation.safe_text_excerpt, '근거 문단 없음')}</p>
                                </li>
                              ))}
                            </ol>
                          </div>
                        </div>
                      ) : (
                        <p className="mt-4 rounded-lg border border-dashed border-border p-3 text-sm font-semibold text-muted-foreground">선택 가능한 관계 맥락 객체가 없습니다.</p>
                      )}
                    </aside>
                  </div>
                ) : (
                  <div className="p-5">
                    <p className="rounded-xl border border-dashed border-border p-4 text-sm font-semibold text-muted-foreground">
                      {traceLoading ? '추적성 맵을 불러오는 중입니다.' : '추적성 맵을 불러오지 못했습니다.'}
                    </p>
                  </div>
                )}
              </section>
            ) : null}

            {(viewMode === '프로젝트 상세' || viewMode === '마일스톤') && (
              <section aria-label="조회된 작업 현황" className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
                <div className="flex items-center justify-between border-b border-border p-5">
                  <h2 className="font-bold text-lg">조회된 작업 현황</h2>
                  <a href="/tasks" className="rounded-md bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:bg-primary/90">작업 보드 열기</a>
                </div>
                <div className="grid gap-4 p-5 md:grid-cols-4">
                  {[
                    { label: '실행 항목', count: openCount, status: 'open' as const },
                    { label: '진행 중', count: inProgressCount, status: 'in_progress' as const },
                    { label: '검토 필요', count: blockedCount, status: 'blocked' as const },
                    { label: '완료', count: doneCount, status: 'done' as const },
                  ].map((milestone) => (
                    <article key={milestone.status} className="rounded-xl border border-border bg-background p-4">
                      <div className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold ${taskStatusClass[milestone.status]}`}>{milestone.label}</div>
                      <p className="mt-4 text-2xl font-black">{milestone.count}</p>
                      <p className="mt-1 text-sm text-muted-foreground">조회된 작업 기준</p>
                    </article>
                  ))}
                </div>
              </section>
            )}

            {(viewMode === '프로젝트 상세' || viewMode === '의사결정 로그') && (
              <section aria-label="프로젝트 의사결정 로그" className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
                <div className="flex items-center justify-between border-b border-border bg-primary/5 p-5">
                  <h2 className="font-bold text-lg text-primary">의사결정 로그</h2>
                  <button type="button" aria-label="프로젝트 의사결정 추가" onClick={() => setViewMode('의사결정 로그')} className="rounded-md bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:bg-primary/90">의사결정 추가</button>
                </div>
                <div className="divide-y divide-border">
                  <article className="p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="flex items-center gap-2 font-bold text-base"><CheckCircle2 className="size-4 text-emerald-500" /> 원본 저장소 연결</h3>
                      <span className="text-xs text-muted-foreground">{authorizedFolders.length}개 폴더</span>
                    </div>
                    <p className="mt-2 rounded-lg border border-border bg-background p-3 text-sm leading-6 text-foreground">
                      WebDAV 프로젝트 폴더를 작업 경계로 사용합니다. 외부 저장소 쓰기는 별도 승인 전까지 실행하지 않습니다.
                    </p>
                    <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><User className="size-3.5" /> 근거: WebDAV 폴더</p>
                  </article>
                  <article className="p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="flex items-center gap-2 font-bold text-base"><ListChecks className="size-4 text-primary" /> 작업 흐름 반영</h3>
                      <span className="text-xs text-muted-foreground">{loadedTasks.length}개 작업</span>
                    </div>
                    <p className="mt-2 rounded-lg border border-border bg-background p-3 text-sm leading-6 text-foreground">
                      조회된 작업을 집계한 현황입니다. 선택한 프로젝트와 각 작업의 연결 여부는 아직 확인할 수 없습니다.
                    </p>
                    <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><User className="size-3.5" /> 근거: 실행 항목</p>
                  </article>
                  <article className="p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="flex items-center gap-2 font-bold text-base"><Search className="size-4 text-primary" /> 관련 문서/메일 연결</h3>
                      <a href="/search" className="rounded-md border border-border bg-background px-2.5 py-1 text-xs font-bold hover:bg-secondary">맥락 검색</a>
                    </div>
                    <p className="mt-2 rounded-lg border border-border bg-background p-3 text-sm leading-6 text-foreground">
                      프로젝트 판단 근거는 맥락 검색에서 메일, 스레드, 문서 근거를 확인한 뒤 연결합니다.
                    </p>
                    <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><User className="size-3.5" /> 상태: 연결 준비</p>
                  </article>
                </div>
              </section>
            )}

            <section aria-label="조회된 작업 목록" className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
              <div className="flex items-center justify-between border-b border-border p-5">
                <h2 className="font-bold text-lg">조회된 작업</h2>
                <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-bold text-muted-foreground">{loadedTasks.length}건</span>
              </div>
              {loadedTasks.length > 0 ? loadedTasksList : (
                <div className="p-5">
                  <div className="rounded-xl border border-dashed border-border bg-background p-4">
                    <div role="status" aria-live="polite">
                      <p className="text-sm font-bold text-foreground">등록된 작업이 아직 없습니다.</p>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        작업 보드에서 작업을 등록하거나 관련 메일과 문서를 찾아보세요. 프로젝트별 작업 연결은 아직 지원하지 않습니다.
                      </p>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <a href="/tasks" className="rounded-md bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:bg-primary/90">작업 보드 열기</a>
                      <a href="/search" className="rounded-md border border-border bg-card px-3 py-1.5 text-xs font-bold hover:bg-secondary">관련 근거 찾기</a>
                    </div>
                  </div>
                </div>
              )}
            </section>
          </div>

          <aside className="space-y-6">
            <section aria-label="프로젝트 액션" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
              <h2 className="mb-4 font-bold text-base">프로젝트 액션</h2>
              <div className="grid gap-2 text-sm">
                <a href="/data" className="flex min-h-10 items-center gap-2 rounded-md bg-primary px-3 font-bold text-primary-foreground hover:bg-primary/90"><FolderOpen className="size-4" /> 새 프로젝트</a>
                <button type="button" aria-label="프로젝트 상세 열기" onClick={() => setViewMode('프로젝트 상세')} className="flex min-h-10 items-center gap-2 rounded-md border border-border bg-background px-3 font-bold hover:bg-secondary"><CheckCircle2 className="size-4 text-primary" /> 프로젝트 열기</button>
                <a href="/tasks" className="flex min-h-10 items-center gap-2 rounded-md border border-border bg-background px-3 font-bold hover:bg-secondary"><ListChecks className="size-4 text-primary" /> 작업 보드 열기</a>
                <button type="button" aria-label="프로젝트 의사결정 추가" onClick={() => setViewMode('의사결정 로그')} className="flex min-h-10 items-center gap-2 rounded-md border border-border bg-background px-3 font-bold hover:bg-secondary"><CheckCircle2 className="size-4 text-primary" /> 의사결정 추가</button>
                <a href="/search" className="flex min-h-10 items-center gap-2 rounded-md border border-border bg-background px-3 font-bold hover:bg-secondary"><Search className="size-4 text-primary" /> 관련 문서/메일 연결</a>
              </div>
            </section>

            <section aria-label="프로젝트 개요" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
              <h2 className="mb-4 font-bold text-base">프로젝트 개요</h2>
              <dl className="space-y-4 text-sm">
                <div>
                  <dt className="mb-1 font-semibold text-muted-foreground">책임 경계</dt>
                  <dd className="flex items-center gap-2 font-bold"><User className="size-4 text-primary" /> {workspaceScopeLabel}</dd>
                </div>
                <div>
                  <dt className="mb-1 font-semibold text-muted-foreground">상태</dt>
                  <dd><span className={`rounded px-2 py-1 text-xs font-bold ${projectStatusClass[activeProject.status]}`}>{activeProject.status}</span></dd>
                </div>
                <div>
                  <dt className="mb-1 font-semibold text-muted-foreground">{activeProject.evidence === 'ticket_tasks' ? '조회된 작업 완료율' : '진행률'}</dt>
                  <dd className="flex items-center gap-3">
                    {activeProject.progress === null ? (
                      <span className="text-sm text-muted-foreground">진행률 확인 불가 — 완료한 작업과 전체 작업 수를 확인할 근거가 없습니다.</span>
                    ) : (
                      <>
                        <progress aria-label="조회된 작업 완료율" className="h-2 min-w-0 flex-1" max={100} value={activeProject.progress} />
                        <span className="font-mono text-xs font-bold">{activeProject.progress}%</span>
                      </>
                    )}
                  </dd>
                  {activeProject.progress !== null ? (
                    <dd className="mt-2 text-xs text-muted-foreground">조회된 {loadedTasks.length}건 중 {doneCount}건 완료. 프로젝트별 집계가 아닙니다.</dd>
                  ) : null}
                </div>
                <div>
                  <dt className="mb-1 font-semibold text-muted-foreground">원본 근거</dt>
                  <dd className="text-sm font-bold">{projectEvidenceLabel}</dd>
                  <dd className="mt-1 text-xs font-semibold text-muted-foreground">{projectBoundaryLabel}</dd>
                </div>
              </dl>
            </section>

            <section aria-label="프로젝트 근거 편집" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-bold text-base">근거 편집</h2>
                  <p id="project-evidence-unsaved" className="mt-1 text-xs font-semibold text-muted-foreground">메모 저장은 아직 지원하지 않습니다. 입력 내용은 이 화면에서만 유지되며 새로고침하면 사라집니다.</p>
                </div>
                <span className="shrink-0 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">{selectedEvidenceOption.label}</span>
              </div>
              <label className="grid gap-2 text-sm font-bold" htmlFor="project-evidence-note">
                프로젝트 근거 메모
                <textarea
                  id="project-evidence-note"
                  aria-label="프로젝트 근거 메모"
                  aria-describedby="project-evidence-unsaved"
                  value={evidenceDraft}
                  onChange={(event) => {
                    setEvidenceDraft(event.target.value);
                  }}
                  className="min-h-24 resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm font-semibold leading-6 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                />
              </label>
              <label className="mt-4 grid gap-2 text-sm font-bold" htmlFor="project-evidence-source">
                연결 원본 변경
                <select
                  id="project-evidence-source"
                  aria-label="연결 원본 변경"
                  aria-describedby="project-evidence-unsaved"
                  value={evidenceSource}
                  onChange={(event) => {
                    setEvidenceSource(event.target.value as ProjectEvidenceSource);
                  }}
                  className="min-h-10 rounded-lg border border-input bg-background px-3 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                >
                  {projectEvidenceSourceOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <p className="mt-2 text-xs font-semibold text-muted-foreground">{selectedEvidenceOption.description}</p>
              <div className="mt-4 rounded-lg border border-border bg-background p-3 text-xs font-semibold leading-5 text-muted-foreground">
                <span className="block font-bold text-foreground">미저장 메모 미리보기</span>
                {evidenceDraftPreview}
              </div>
              <button type="button" disabled aria-describedby="project-evidence-unsaved" className="mt-4 flex min-h-10 w-full items-center justify-center gap-2 rounded-md bg-secondary px-3 text-sm font-bold text-muted-foreground disabled:cursor-not-allowed">
                <CheckCircle2 className="size-4" /> 근거 저장
              </button>
            </section>

            <section aria-label="연결된 자원" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
              <h2 className="mb-4 font-bold text-base">연결된 자원</h2>
              <ul className="space-y-3 text-sm">
                <li className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 font-semibold"><FolderOpen className="size-4 text-primary" /> WebDAV 폴더</span>
                  <span className="font-mono text-xs text-muted-foreground">{authorizedFolders.length}</span>
                </li>
                <li className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 font-semibold"><ListChecks className="size-4 text-primary" /> 실행 항목</span>
                  <span className="font-mono text-xs text-muted-foreground">{loadedTasks.length}</span>
                </li>
                <li className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 font-semibold"><CalendarDays className="size-4 text-primary" /> 원본 종류</span>
                  <span className="font-mono text-xs text-muted-foreground">{sourceTypeCount}</span>
                </li>
              </ul>
            </section>
          </aside>
        </div>
      </main>
    </div>
  );
}