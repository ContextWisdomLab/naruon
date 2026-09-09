"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { EmailList } from '@/components/EmailList';
import type { MailFolder } from '@/components/EmailList';
import { EmailDetail } from '@/components/EmailDetail';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import dynamic from 'next/dynamic';
import { CalendarDays, CheckCircle2, Inbox, Network, Send, Settings, Sparkles } from 'lucide-react';
import { useTasks, type TaskItem } from '@/hooks/useTasks';
import { apiClient } from '@/lib/api-client';
import { isMailListItem } from '@/lib/mail-response';
import { setMobileWorkspaceView, useMobileWorkspaceView } from '@/lib/mobile-workspace';
import { toSafeReactText } from '@/lib/safe-text';
import { setWorkspaceStartupView, useWorkspaceStartupView, type WorkspaceStartupView } from '@/lib/workspace-preferences';
import { MobileCalendarPanel, MobileSearchPanel } from '@/components/mobile-workspace-panels';
const NetworkGraph = dynamic(() => import('@/components/NetworkGraph'), { ssr: false });

type WorkspaceActionCommand = { id: number; action: string; target: 'desktop' | 'tablet'; modeVersion: number };
type MobileActionCommand = { id: number; action: string; modeVersion: number };
type DashboardDataStatus = 'loading' | 'ready' | 'auth' | 'error';
type DashboardDataStatuses = Record<
  'emails' | 'pendingReplies' | 'tasks' | 'calendarSources' | 'projectFolders',
  DashboardDataStatus
>;
type StartupSearchResult = {
  id: number;
  subject: string | null;
  sender: string;
  date: string;
  snippet: string;
};

function useStartupSearch(query: string, limit: number) {
  const [status, setStatus] = useState<'loading' | 'success' | 'empty' | 'error'>('loading');
  const [results, setResults] = useState<StartupSearchResult[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    void apiClient.post<{ results: StartupSearchResult[] }>('/api/search', { query, limit }, { signal: controller.signal })
      .then((response) => {
        if (cancelled) return;
        if (!Array.isArray(response.results) || !response.results.every(isMailListItem)) throw new Error('Invalid search response');
        setResults(response.results);
        setStatus(response.results.length > 0 ? 'success' : 'empty');
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setResults([]);
        setStatus('error');
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [limit, query]);

  return { results, status };
}

type CalendarWritebackSource = {
  source_id: string;
  provider?: string;
  protocol?: string;
  capabilities?: string[];
  writeback_enabled?: boolean;
  etag?: string | null;
};

type ProjectFolder = {
  folder_uid: string;
  project_name: string;
  webdav_path: string;
  owner_user_id: string;
  organization_id: string | null;
};

const dashboardQuickActions = [
  { label: '메일함 열기', href: '/mail', icon: Inbox, color: 'text-blue-500' },
  { label: '보낸 메일 답변 추적', href: '/mail?folder=sent', icon: Send, color: 'text-rose-500' },
  { label: '일정 후보 검토', href: '/calendar', icon: CalendarDays, color: 'text-blue-500' },
  { label: '실행 항목 보드', href: '/tasks', icon: CheckCircle2, color: 'text-green-500' },
  { label: '프로젝트 의사결정', href: '/projects', icon: Network, color: 'text-purple-500' },
  { label: 'AI 허브', href: '/ai-hub', icon: Sparkles, color: 'text-purple-500' },
  { label: '데이터 품질 점검', href: '/data', icon: Network, color: 'text-blue-500' },
  { label: '보안 감사 로그', href: '/security', icon: CheckCircle2, color: 'text-emerald-500' },
];

interface EmailItem {
  id: number;
  subject: string | null;
  sender: string;
  date?: string;
  snippet: string;
  unread?: boolean;
}

function isDashboardRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isDashboardTask(value: unknown): value is TaskItem {
  return isDashboardRecord(value)
    && typeof value.id === 'string' && value.id.length > 0
    && typeof value.title === 'string'
    && typeof value.status === 'string' && ['open', 'in_progress', 'blocked', 'done'].includes(value.status)
    && typeof value.priority === 'string' && ['low', 'normal', 'high', 'urgent'].includes(value.priority)
    && typeof value.created_at === 'string' && typeof value.updated_at === 'string';
}

function isDashboardCalendarSource(value: unknown): value is CalendarWritebackSource {
  return isDashboardRecord(value)
    && typeof value.source_id === 'string' && value.source_id.length > 0
    && (value.provider === undefined || typeof value.provider === 'string')
    && (value.protocol === undefined || typeof value.protocol === 'string')
    && (value.capabilities === undefined || (Array.isArray(value.capabilities)
      && value.capabilities.every((capability: unknown) => typeof capability === 'string')))
    && (value.writeback_enabled === undefined || typeof value.writeback_enabled === 'boolean')
    && (value.etag === undefined || value.etag === null || typeof value.etag === 'string');
}

function isDashboardProjectFolder(value: unknown): value is ProjectFolder {
  return isDashboardRecord(value)
    && typeof value.folder_uid === 'string'
    && typeof value.project_name === 'string'
    && typeof value.webdav_path === 'string'
    && typeof value.owner_user_id === 'string'
    && (value.organization_id === null || typeof value.organization_id === 'string');
}

function isWritableCalendarSource(source: CalendarWritebackSource) {
  return Boolean(
    source.writeback_enabled
    && source.protocol !== 'local'
    && (source.capabilities ?? []).includes('write'),
  );
}

function safeWorkspaceTitle(title: string | null | undefined, fallback = '제목 없는 항목') {
  const displayTitle = toSafeReactText(title?.trim() || null, fallback)
    .replace(/<[^>]*>/g, ' ')
    .replace(/[<>]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return displayTitle || fallback;
}

function getCalendarSourceLabel(index: number) {
  return `일정 원본 ${index + 1}`;
}

function getCalendarProtocolLabel(protocol: string | undefined) {
  switch (protocol) {
    case 'caldav':
      return 'CalDAV 원본';
    case 'carddav':
      return 'CardDAV 원본';
    case 'webdav':
      return 'WebDAV 원본';
    default:
      return '원본 계정';
  }
}

function getCalendarCapabilityLabel(capability: string) {
  switch (capability) {
    case 'read':
      return '읽기';
    case 'write':
      return '일정 반영';
    case 'etag':
      return '충돌 검사';
    default:
      return '원본 기능';
  }
}

function getCalendarConflictLabel(source: CalendarWritebackSource) {
  return source.etag ? '충돌 토큰 있음' : '충돌 토큰 대기';
}

function buildCompletionRate(tasks: TaskItem[]) {
  if (tasks.length === 0) return 0;
  return Math.round((tasks.filter((task) => task.status === 'done').length / tasks.length) * 100);
}

function getApiErrorStatus(error: unknown) {
  const shapedError = error as { status?: unknown; response?: { status?: unknown } } | null;
  if (typeof shapedError?.status === 'number') return shapedError.status;
  if (typeof shapedError?.response?.status === 'number') return shapedError.response.status;
  return null;
}

function isDashboardDataUnavailable(status: DashboardDataStatus) {
  return status === 'auth' || status === 'error';
}

function createDashboardReadSignal(requestSignal: AbortSignal, timeoutMs: number) {
  if (typeof AbortSignal.any === 'function' && typeof AbortSignal.timeout === 'function') {
    return AbortSignal.any([requestSignal, AbortSignal.timeout(timeoutMs)]);
  }

  const fallbackController = new AbortController();
  const abortFallback = (reason: unknown) => {
    if (!fallbackController.signal.aborted) fallbackController.abort(reason);
  };
  const handleRequestAbort = () => abortFallback(requestSignal.reason);
  requestSignal.addEventListener('abort', handleRequestAbort, { once: true });
  const timeoutId = window.setTimeout(
    () => abortFallback(new DOMException('The operation timed out.', 'TimeoutError')),
    timeoutMs,
  );
  fallbackController.signal.addEventListener('abort', () => {
    window.clearTimeout(timeoutId);
    requestSignal.removeEventListener('abort', handleRequestAbort);
  }, { once: true });
  if (requestSignal.aborted) handleRequestAbort();
  return fallbackController.signal;
}

function useDashboardData() {
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [pendingReplies, setPendingReplies] = useState<EmailItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [calendarSources, setCalendarSources] = useState<CalendarWritebackSource[]>([]);
  const [projectFolders, setProjectFolders] = useState<ProjectFolder[]>([]);
  const [dataStatus, setDataStatus] = useState<DashboardDataStatuses>({
    emails: 'loading',
    pendingReplies: 'loading',
    tasks: 'loading',
    calendarSources: 'loading',
    projectFolders: 'loading',
  });
  const [reloadVersion, setReloadVersion] = useState(0);
  const requestVersionRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const requestVersion = reloadVersion;
    const requestController = new AbortController();
    const dashboardReadSignal = createDashboardReadSignal(requestController.signal, 15_000);
    const isStaleRequest = () => cancelled || requestVersion !== requestVersionRef.current;
    const setSourceStatus = (source: keyof DashboardDataStatuses, status: DashboardDataStatus) => {
      if (isStaleRequest()) return;
      setDataStatus((currentStatus) => ({ ...currentStatus, [source]: status }));
    };
    const failureStatus = (error: unknown): DashboardDataStatus => {
      const status = getApiErrorStatus(error);
      return status === 401 || status === 403 ? 'auth' : 'error';
    };

    void apiClient.get<{ emails: EmailItem[] }>('/api/emails', { signal: dashboardReadSignal })
      .then((response) => {
        if (isStaleRequest()) return;
        if (!Array.isArray(response.emails) || !response.emails.every(isMailListItem)) throw new Error('Invalid dashboard email response');
        setEmails(response.emails);
        setSourceStatus('emails', 'ready');
      })
      .catch((error: unknown) => {
        if (isStaleRequest()) return;
        setEmails([]);
        setSourceStatus('emails', failureStatus(error));
      });

    void apiClient.get<{ emails: EmailItem[] }>('/api/emails/pending-replies?limit=3', { signal: dashboardReadSignal })
      .then((response) => {
        if (isStaleRequest()) return;
        if (!Array.isArray(response.emails) || !response.emails.every(isMailListItem)) throw new Error('Invalid pending-reply response');
        setPendingReplies(response.emails);
        setSourceStatus('pendingReplies', 'ready');
      })
      .catch((error: unknown) => {
        if (isStaleRequest()) return;
        setPendingReplies([]);
        setSourceStatus('pendingReplies', failureStatus(error));
      });

    void apiClient.get<TaskItem[]>('/api/tasks', { signal: dashboardReadSignal })
      .then((response) => {
        if (isStaleRequest()) return;
        if (!Array.isArray(response) || !response.every(isDashboardTask)) throw new Error('Invalid dashboard task response');
        setTasks(response);
        setSourceStatus('tasks', 'ready');
      })
      .catch((error: unknown) => {
        if (isStaleRequest()) return;
        setTasks([]);
        setSourceStatus('tasks', failureStatus(error));
      });

    void apiClient.get<CalendarWritebackSource[]>('/api/calendar/writeback-sources', { signal: dashboardReadSignal })
      .then((response) => {
        if (isStaleRequest()) return;
        if (!Array.isArray(response) || !response.every(isDashboardCalendarSource)) throw new Error('Invalid calendar-source response');
        setCalendarSources(response);
        setSourceStatus('calendarSources', 'ready');
      })
      .catch((error: unknown) => {
        if (isStaleRequest()) return;
        setCalendarSources([]);
        setSourceStatus('calendarSources', failureStatus(error));
      });

    void apiClient.get<ProjectFolder[]>('/api/webdav/folders', { signal: dashboardReadSignal })
      .then((response) => {
        if (isStaleRequest()) return;
        if (!Array.isArray(response) || !response.every(isDashboardProjectFolder)) throw new Error('Invalid project-folder response');
        setProjectFolders(response);
        setSourceStatus('projectFolders', 'ready');
      })
      .catch((error: unknown) => {
        if (isStaleRequest()) return;
        setProjectFolders([]);
        setSourceStatus('projectFolders', failureStatus(error));
      });

    return () => {
      cancelled = true;
      requestController.abort();
    };
  }, [reloadVersion]);

  const retryDashboardData = useCallback(() => {
    setDataStatus({
      emails: 'loading',
      pendingReplies: 'loading',
      tasks: 'loading',
      calendarSources: 'loading',
      projectFolders: 'loading',
    });
    requestVersionRef.current += 1;
    setReloadVersion(requestVersionRef.current);
  }, []);

  return { emails, pendingReplies, tasks, setTasks, calendarSources, projectFolders, dataStatus, retryDashboardData };
}

function formatStartupDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '날짜 미정';
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(date);
}

function formatDashboardTimestamp(value: Date) {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  }).format(value);
}

function StartupResultList({ results }: { results: StartupSearchResult[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {results.map((result) => {
        const subject = toSafeReactText(result.subject?.trim() || null, '(제목 없음)');
        const sender = toSafeReactText(result.sender);
        const snippet = toSafeReactText(result.snippet);
        return (
          <article key={result.id} className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-base font-black text-foreground">{subject}</h2>
              <span suppressHydrationWarning className="shrink-0 rounded-full bg-primary/10 px-2 py-1 text-[11px] font-bold text-primary">{formatStartupDate(result.date)}</span>
            </div>
            <p className="mt-1 text-xs font-bold text-primary">{sender}</p>
            <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted-foreground">{snippet}</p>
          </article>
        );
      })}
    </div>
  );
}

function StartupDashboard({ onOpenView }: { onOpenView: (view: WorkspaceStartupView) => void }) {
  const { emails, pendingReplies, tasks, setTasks: setDashboardTasks, calendarSources, projectFolders, dataStatus, retryDashboardData } = useDashboardData();
  const calendarCandidateEvidence = useStartupSearch('일정 충돌 일정 조율 회의 후보', 3);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [currentTimestamp, setCurrentTimestamp] = useState('');
  const settingsMenuId = 'workspace-startup-settings-menu';
  const unreadCount = emails.filter((e) => e.unread).length;
  const pendingReplyCount = pendingReplies.length;
  const pendingTasks = tasks.filter((t) => t.status !== 'done');
  const completedTaskCount = tasks.filter((task) => task.status === 'done').length;
  const writableCalendarSourceCount = calendarSources.filter(isWritableCalendarSource).length;
  const taskCompletionRate = buildCompletionRate(tasks);
  const emailLoading = dataStatus.emails === 'loading';
  const emailUnavailable = isDashboardDataUnavailable(dataStatus.emails);
  const pendingReplyLoading = dataStatus.pendingReplies === 'loading';
  const pendingReplyUnavailable = isDashboardDataUnavailable(dataStatus.pendingReplies);
  const taskLoading = dataStatus.tasks === 'loading';
  const taskUnavailable = isDashboardDataUnavailable(dataStatus.tasks);
  const calendarSourceLoading = dataStatus.calendarSources === 'loading';
  const calendarSourceError = isDashboardDataUnavailable(dataStatus.calendarSources);
  const projectFolderLoading = dataStatus.projectFolders === 'loading';
  const projectFolderError = isDashboardDataUnavailable(dataStatus.projectFolders);
  const dashboardAuthenticationRequired = Object.values(dataStatus).includes('auth');
  const dashboardDataError = Object.values(dataStatus).some(isDashboardDataUnavailable);
  const dashboardStats = useMemo(() => ([
    { title: '받은 메일', value: emailUnavailable ? '오류' : emailLoading ? '-' : emails.length.toString(), diff: emailUnavailable ? '확인 필요' : unreadCount > 0 ? `+${unreadCount}` : '-', diffText: '안 읽음', icon: Inbox, color: emailUnavailable ? 'text-red-500' : 'text-primary' },
    { title: '답변 대기', value: pendingReplyUnavailable ? '오류' : pendingReplyLoading ? '-' : pendingReplyCount.toString(), diff: pendingReplyUnavailable ? '확인 필요' : pendingReplyCount > 0 ? `${pendingReplyCount}건` : '-', diffText: '보낸 메일', icon: Send, color: pendingReplyUnavailable ? 'text-red-500' : 'text-rose-500' },
    { title: '일정 원본', value: calendarSourceError ? '오류' : calendarSourceLoading ? '-' : calendarSources.length.toString(), diff: calendarSourceError ? '확인 필요' : calendarSourceLoading ? '-' : `${writableCalendarSourceCount}개`, diffText: calendarSourceError ? '원본 확인' : '반영 가능', icon: CalendarDays, color: calendarSourceError ? 'text-red-500' : 'text-blue-500' },
    { title: '대기 작업', value: taskUnavailable ? '오류' : taskLoading ? '-' : pendingTasks.length.toString(), diff: taskUnavailable ? '확인 필요' : '-', diffText: 'source-linked', icon: CheckCircle2, color: taskUnavailable ? 'text-red-500' : 'text-green-500' },
    { title: '프로젝트 원본', value: projectFolderError ? '오류' : projectFolderLoading ? '-' : projectFolders.length.toString(), diff: projectFolderError ? '확인 필요' : projectFolderLoading ? '-' : `${projectFolders.length}개`, diffText: 'WebDAV 폴더', icon: Network, color: projectFolderError ? 'text-red-500' : 'text-purple-500' },
    { title: '작업 완료율', value: taskUnavailable ? '오류' : taskLoading ? '-' : `${taskCompletionRate}%`, diff: taskUnavailable ? '확인 필요' : taskLoading ? '-' : `${completedTaskCount}/${tasks.length}`, diffText: '완료', icon: CheckCircle2, color: taskUnavailable ? 'text-red-500' : 'text-emerald-500' },
  ]), [
    calendarSources.length,
    completedTaskCount,
    emailLoading,
    emailUnavailable,
    emails.length,
    pendingReplyCount,
    pendingReplyLoading,
    pendingReplyUnavailable,
    pendingTasks.length,
    projectFolders.length,
    calendarSourceError,
    calendarSourceLoading,
    projectFolderError,
    projectFolderLoading,
    taskCompletionRate,
    taskLoading,
    taskUnavailable,
    tasks.length,
    unreadCount,
    writableCalendarSourceCount,
  ]);
  const {
    taskUpdateStatusById,
    replySlaStatus,
    replySlaMessage,
    handleTaskCompletionToggle,
    handleReplySlaEscalation,
  } = useTasks(setDashboardTasks, safeWorkspaceTitle);

  useEffect(() => {
    const updateTimestamp = () => setCurrentTimestamp(formatDashboardTimestamp(new Date()));
    updateTimestamp();
    const intervalId = window.setInterval(updateTimestamp, 60_000);
    return () => window.clearInterval(intervalId);
  }, []);

  const mapPriorityToKorean = (p: string) => {
    switch(p) {
      case 'urgent': return '긴급';
      case 'high': return '높음';
      case 'normal': return '보통';
      case 'low': return '낮음';
      default: return p;
    }
  };

  return (
    <section role="region" aria-label="홈 개요" className="h-full overflow-y-auto bg-background p-4 sm:p-6">
      <div className="mx-auto max-w-7xl space-y-6">

        {/* Header Section */}
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="break-keep text-2xl font-bold leading-tight text-foreground">안녕하세요, 김나루님 👋</h1>
          </div>
          <div className="relative flex flex-wrap items-center gap-3">
            <span suppressHydrationWarning className="break-keep text-sm font-medium text-muted-foreground">{currentTimestamp || '현재 시간 확인 중'}</span>
            <button type="button"
              aria-controls={settingsMenuId}
              aria-expanded={isSettingsOpen}
              aria-haspopup="menu"
              onClick={() => setIsSettingsOpen(!isSettingsOpen)}
              className="flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              <Settings className="size-4" aria-hidden="true" />
              홈 설정
            </button>
            {isSettingsOpen && (
              <div id={settingsMenuId} role="menu" className="absolute right-0 top-full z-50 mt-2 w-48 rounded-xl border border-border bg-card p-2 shadow-lg">
                <p className="px-2 py-1 text-xs font-semibold text-muted-foreground">시작 화면 설정</p>
                <div className="mt-1 flex flex-col gap-1">
                  <button type="button" role="menuitem" onClick={() => { setWorkspaceStartupView('dashboard'); setIsSettingsOpen(false); }} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
                    홈
                  </button>
                  <button type="button" role="menuitem" onClick={() => { setWorkspaceStartupView('email'); setIsSettingsOpen(false); }} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
                    메일 우선
                  </button>
                  <button type="button" role="menuitem" onClick={() => { setWorkspaceStartupView('calendar'); setIsSettingsOpen(false); }} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
                    일정 우선
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {dashboardDataError ? (
          <div role="alert" aria-label="대시보드 데이터 상태" className="flex flex-col gap-3 border border-destructive/40 bg-destructive/10 p-4 text-sm sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-bold text-destructive">{dashboardAuthenticationRequired ? '로그인이 필요합니다.' : '업무 현황을 모두 불러오지 못했습니다.'}</p>
              <p className="mt-1 text-muted-foreground">
                {dashboardAuthenticationRequired
                  ? '세션이 만료됐거나 이 작업공간에 접근할 수 없습니다.'
                  : '연결을 확인한 뒤 다시 시도하세요. 확인된 항목은 그대로 표시됩니다.'}
              </p>
            </div>
            {dashboardAuthenticationRequired ? (
              <a
                href="/settings"
                className="shrink-0 border border-border bg-background px-3 py-2 font-semibold text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              >
                로그인 설정 열기
              </a>
            ) : (
              <button
                type="button"
                onClick={retryDashboardData}
                className="shrink-0 border border-border bg-background px-3 py-2 font-semibold text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              >
                다시 시도
              </button>
            )}
          </div>
        ) : null}

        {/* KPI Cards */}
        <div aria-label="홈 지표" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {dashboardStats.map((stat) => (
            <article key={stat.title} aria-label={stat.title} className="min-w-0 rounded-2xl border border-border bg-card p-4 shadow-sm">
              <div className="flex min-w-0 items-start gap-2 text-sm font-semibold text-muted-foreground">
                <stat.icon className={`mt-0.5 size-4 shrink-0 ${stat.color}`} />
                <span className="min-w-0 break-keep leading-snug">{stat.title}</span>
              </div>
              <div className="mt-4 text-3xl font-bold">{stat.value}</div>
              <div className={`mt-2 break-keep text-xs font-medium ${stat.diff.startsWith('+') ? 'text-primary' : stat.diff.startsWith('-') && stat.diff !== '-' ? 'text-red-500' : 'text-muted-foreground'}`}>
                {stat.diff} <span className="text-muted-foreground font-normal">{stat.diffText}</span>
              </div>
            </article>
          ))}
        </div>

        {/* 오늘의 핵심 맥락 종합 */}
        <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
          <h2 className="text-lg font-bold">오늘의 핵심 맥락 종합</h2>
          <div className="mt-4 grid grid-cols-1 gap-4 divide-y divide-border md:grid-cols-3 md:gap-6 md:divide-x md:divide-y-0">
            <div className="flex gap-4">
              <div className="grid size-10 shrink-0 place-items-center rounded-full bg-rose-100 text-rose-600"><Send className="size-5" /></div>
              <div>
                <p className="break-keep font-bold">답변 대기 {pendingReplyUnavailable ? '확인 필요' : pendingReplyLoading ? '-' : `${pendingReplyCount}건`}</p>
                <p className="text-xs text-muted-foreground mt-1">{pendingReplyUnavailable ? '보낸 메일 응답 상태를 확인할 수 없습니다.' : '보낸 메일 중 회신 확인이 필요한 항목입니다.'}</p>
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <a href="/mail?folder=sent" className="inline-flex text-xs font-semibold text-primary hover:underline rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">보낸 메일 보기</a>
                  <button
                    type="button"
                    aria-label="홈에서 보낸 메일 미답변 팔로업 작업 생성"
                    disabled={dataStatus.pendingReplies !== 'ready' || pendingReplyCount === 0 || replySlaStatus === 'loading'}
                    aria-busy={pendingReplyLoading || replySlaStatus === 'loading'}
                    onClick={() => void handleReplySlaEscalation()}
                    className="text-xs font-semibold text-primary hover:underline disabled:cursor-not-allowed disabled:text-muted-foreground disabled:no-underline rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                  >
                    {replySlaStatus === 'loading' ? '확인 중' : '팔로업 작업 생성'}
                  </button>
                </div>
                {replySlaMessage ? (
                  <p role="status" className={`mt-2 text-xs font-semibold ${replySlaStatus === 'error' ? 'text-red-600' : 'text-muted-foreground'}`}>
                    {replySlaMessage}
                  </p>
                ) : null}
              </div>
            </div>
            <div className="flex gap-4 pt-4 md:pl-6 md:pt-0">
              <div className="grid size-10 shrink-0 place-items-center rounded-full bg-blue-100 text-blue-600"><CalendarDays className="size-5" /></div>
              <div>
                <p className="break-keep font-bold">{calendarSourceError ? '일정 원본 확인 필요' : `일정 원본 ${calendarSourceLoading ? '-' : calendarSources.length}개`}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {calendarSourceError ? '일정 원본 목록 응답을 확인할 수 없습니다.' : calendarSourceLoading ? '일정 원본 목록을 확인하는 중입니다.' : `${writableCalendarSourceCount}개 일정 반영 가능 · 원본 목록 확인됨`}
                </p>
                {!calendarSourceError && calendarSources[0] ? (
                  <p className="mt-1 text-xs font-semibold text-muted-foreground">
                    {getCalendarSourceLabel(0)} · {getCalendarConflictLabel(calendarSources[0])}
                  </p>
                ) : null}
                <button type="button" onClick={() => onOpenView('calendar')} className="mt-2 text-xs font-semibold text-primary hover:underline rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">일정 확인하기</button>
              </div>
            </div>
            <div className="flex gap-4 pt-4 md:pl-6 md:pt-0">
              <div className="grid size-10 shrink-0 place-items-center rounded-full bg-green-100 text-green-600"><CheckCircle2 className="size-5" /></div>
              <div>
                <p className="break-keep font-bold">완료 가능 작업 {taskUnavailable ? '확인 필요' : taskLoading ? '-' : `${pendingTasks.length}건`}</p>
                <p className="text-xs text-muted-foreground mt-1">{taskUnavailable ? '작업 현황을 확인할 수 없습니다.' : '오늘 마감 전 완료해보세요.'}</p>
                <a href="/tasks" className="mt-2 inline-flex rounded-sm text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">작업 바로가기</a>
              </div>
            </div>
          </div>
        </div>

        {/* Middle Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold">오늘의 판단 포인트</h2>
              <a href="/tasks?new=true" className="text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">실행 항목 만들기</a>
            </div>
            <div className="space-y-3">
              <div className="text-xs font-bold text-muted-foreground">답변 대기 메일</div>
              {pendingReplyLoading ? (
                <div className="text-sm text-muted-foreground p-2">답변 대기 메일을 불러오는 중...</div>
              ) : pendingReplyUnavailable ? (
                <div className="text-sm text-muted-foreground p-2">답변 대기 메일을 확인하지 못했습니다.</div>
              ) : pendingReplies.length === 0 ? (
                <div className="text-sm text-muted-foreground p-2">답변 대기 중인 보낸 메일이 없습니다.</div>
              ) : pendingReplies.map((reply) => {
                const safeSubject = toSafeReactText(reply.subject?.trim() || null, '(제목 없음)');
                const safeSnippet = toSafeReactText(reply.snippet);
                return (
                  <div key={reply.id} className="flex flex-col gap-2 rounded-lg bg-secondary/50 p-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                      <span className="w-fit shrink-0 rounded bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-700">답변 대기</span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-bold">{safeSubject}</p>
                        <p className="line-clamp-2 text-[11px] text-muted-foreground">{safeSnippet}</p>
                      </div>
                    </div>
                    <span suppressHydrationWarning className="shrink-0 text-xs text-muted-foreground">{formatStartupDate(reply.date || '')}</span>
                  </div>
                );
              })}
            </div>
            <a href="/mail?folder=sent" className="mt-4 block w-full text-center text-sm font-semibold text-primary hover:underline rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">보낸 메일 전체 보기</a>
          </div>

          <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold">대기 작업 {pendingTasks.length > 0 && <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">{pendingTasks.length}건</span>}</h2>
            </div>
            <div className="space-y-3">
              {taskLoading ? (
                <div className="text-sm text-muted-foreground p-2">작업을 불러오는 중...</div>
              ) : taskUnavailable ? (
                <div className="text-sm text-muted-foreground p-2">작업 현황을 확인하지 못했습니다.</div>
              ) : pendingTasks.length === 0 ? (
                <div className="text-sm text-muted-foreground p-2">대기 작업이 없습니다.</div>
              ) : pendingTasks.slice(0, 3).map((task) => {
                const pKor = mapPriorityToKorean(task.priority);
                const pClass = pKor === '긴급' || pKor === '높음' ? 'text-red-500' : pKor === '보통' ? 'text-green-500' : 'text-muted-foreground';
                const displayTitle = safeWorkspaceTitle(task.title, '제목 없는 작업');
                return (
                  <div key={task.id} className="flex items-center justify-between">
                    <label className="flex cursor-pointer items-center gap-3 group">
                      <input
                        type="checkbox"
                        checked={task.status === 'done'}
                        onChange={() => void handleTaskCompletionToggle(task)}
                        className="size-4 cursor-pointer rounded border-border text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                        aria-label={`${displayTitle} 작업 선택`}
                      />
                      <span className="text-sm font-medium transition-colors group-hover:text-primary">{displayTitle}</span>
                    </label>
                    <div className="flex items-center gap-2 text-xs">
                      <span className={`font-semibold ${pClass}`}>{pKor}</span>
                    </div>
                  </div>
                );
              })}
            </div>
            {Array.from(taskUpdateStatusById.entries()).map(([taskId, taskUpdateStatus]) => (
              <p key={taskId} role="status" className="mt-3 text-xs font-semibold text-muted-foreground">{taskUpdateStatus}</p>
            ))}
            <a href="/tasks" className="mt-4 block w-full rounded-sm text-center text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">전체 작업 보기</a>
          </div>

          <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold">
                일정 충돌{' '}
                {calendarCandidateEvidence.status === 'success'
                  ? <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">일정 조율 후보 {calendarCandidateEvidence.results.length}건</span>
                  : !calendarSourceError && calendarSources.length > 0
                    ? <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">일정 원본 {calendarSources.length}개</span>
                    : null}
              </h2>
            </div>
            <div className="space-y-3">
              {calendarCandidateEvidence.status === 'loading' ? (
                <div className="text-sm text-muted-foreground p-2">일정 조율 후보를 불러오는 중입니다.</div>
              ) : calendarCandidateEvidence.status === 'error' ? (
                <div className="text-sm text-muted-foreground p-2">일정 조율 후보를 불러오지 못했습니다.</div>
              ) : calendarCandidateEvidence.status === 'success' ? (
                calendarCandidateEvidence.results.slice(0, 3).map((candidate) => {
                  const subject = toSafeReactText(candidate.subject?.trim() || null, '(제목 없음)');
                  const sender = toSafeReactText(candidate.sender);
                  const snippet = toSafeReactText(candidate.snippet);
                  return (
                    <article key={candidate.id} className="rounded-xl border border-blue-100 bg-blue-50/60 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-bold">{subject}</p>
                          <p className="mt-1 truncate text-[11px] font-semibold text-blue-700">{sender}</p>
                        </div>
                        <span suppressHydrationWarning className="shrink-0 text-xs text-muted-foreground">{formatStartupDate(candidate.date)}</span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">{snippet}</p>
                    </article>
                  );
                })
              ) : calendarSourceError ? (
                <div className="text-sm text-muted-foreground p-2">일정 원본 목록 확인에 실패했습니다.</div>
              ) : calendarSourceLoading ? (
                <div className="text-sm text-muted-foreground p-2">일정 원본 목록을 확인하는 중입니다.</div>
              ) : calendarSources.length === 0 ? (
                <div className="text-sm text-muted-foreground p-2">맥락 검색된 일정 조율 후보와 연결된 일정 원본이 없습니다.</div>
              ) : calendarSources.slice(0, 3).map((source, index) => {
                const writable = isWritableCalendarSource(source);
                return (
                  <div key={source.source_id} className="flex items-start gap-3">
                    <div className={`mt-1 size-2.5 rounded-full ${writable ? 'bg-blue-500' : 'bg-slate-300'}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex justify-between gap-2">
                        <p className="truncate text-sm font-bold">{getCalendarSourceLabel(index)}</p>
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${writable ? 'bg-blue-100 text-blue-700' : 'bg-secondary text-muted-foreground'}`}>{writable ? '반영 가능' : '읽기 전용'}</span>
                      </div>
                      <p className="mt-1 text-xs font-semibold text-muted-foreground">{getCalendarProtocolLabel(source.protocol)} · {getCalendarConflictLabel(source)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{(source.capabilities ?? ['read']).map(getCalendarCapabilityLabel).join(' · ')}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <a href="/calendar" className="mt-4 block w-full rounded-sm text-center text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">일정 조율하기</a>
          </div>
        </div>

        {/* Bottom Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          <div className="lg:col-span-2 rounded-2xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold">최근 메일 {unreadCount > 0 && <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">새 메일 {unreadCount}</span>}</h2>
            </div>
            <div className="space-y-3">
              {emailLoading ? (
                <div className="text-sm text-muted-foreground p-2">메일을 불러오는 중...</div>
              ) : emailUnavailable ? (
                <div className="text-sm text-muted-foreground p-2">최근 메일을 확인하지 못했습니다.</div>
              ) : emails.length === 0 ? (
                <div className="text-sm text-muted-foreground p-2">수신된 메일이 없습니다.</div>
              ) : emails.slice(0, 5).map((mail) => (
                <div key={mail.id} className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="size-8 shrink-0 rounded-full bg-secondary grid place-items-center font-bold text-xs">
                      {toSafeReactText(mail.sender).charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1 flex items-center gap-2">
                      <span className="text-sm font-bold truncate w-32 shrink-0">{toSafeReactText(mail.sender)}</span>
                      <span className="text-sm font-bold truncate">{toSafeReactText(mail.subject, '(제목 없음)')}</span>
                      <span className="text-sm text-muted-foreground truncate hidden lg:inline">{toSafeReactText(mail.snippet)}</span>
                    </div>
                  </div>
                  <div suppressHydrationWarning className="flex items-center gap-2 shrink-0 text-xs text-muted-foreground">
                    {formatStartupDate(mail.date || '')}
                    {mail.unread && <span className="size-2 rounded-full bg-primary" />}
                  </div>
                  <div className="flex gap-2 ml-2">
                    <a href={`/mail?id=${encodeURIComponent(mail.id)}`} className="rounded bg-primary/10 px-2 py-1 text-xs font-bold text-primary hover:bg-primary/20">열기</a>
                  </div>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => onOpenView('email')} className="mt-4 w-full text-center text-sm font-semibold text-primary hover:underline rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">메일함 바로가기</button>
          </div>

          <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold">빠른 실행</h2>
            </div>
            <div aria-label="홈 빠른 실행" className="grid grid-cols-2 gap-3">
              {dashboardQuickActions.map((action) => (
                <a key={action.href} href={action.href} className="flex items-center justify-start gap-3 rounded-xl border border-border bg-card px-4 py-3 text-xs font-bold transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40">
                  <action.icon className={`size-5 shrink-0 ${action.color}`} />
                  <span className="truncate">{action.label}</span>
                </a>
              ))}
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}

function StartupCalendar({ onOpenView }: { onOpenView: (view: WorkspaceStartupView) => void }) {
  const { results, status } = useStartupSearch('회의 마감 후속 조치 일정', 3);

  return (
    <section aria-label="일정관리 시작 화면" className="h-full overflow-y-auto rounded-3xl border border-border/80 bg-card/80 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
      <div className="max-w-4xl space-y-5">
        <div className="rounded-3xl border border-primary/15 bg-primary/5 p-6">
          <p className="text-xs font-black uppercase tracking-[0.2em] text-primary">Calendar</p>
          <h1 className="mt-3 text-3xl font-black text-foreground">일정관리 시작 화면</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">메일에서 추출한 회의, 마감, 후속 조치를 먼저 확인합니다.</p>
          <button
            type="button"
            onClick={() => onOpenView('email')}
            className="mt-5 inline-flex h-11 items-center gap-2 rounded-2xl bg-primary px-4 text-sm font-bold text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          >
            <Inbox className="size-4" aria-hidden="true" />
            메일 작업공간 열기
          </button>
        </div>
        {status === 'loading' ? <div role="status" className="rounded-2xl border border-border bg-card px-4 py-3 text-sm font-semibold text-muted-foreground shadow-sm">일정 후보를 불러오는 중입니다.</div> : null}
        {status === 'error' ? <div role="alert" className="rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive shadow-sm">일정 후보를 불러오지 못했습니다.</div> : null}
        {status === 'empty' ? <div className="rounded-2xl border border-border bg-card px-4 py-3 text-sm font-semibold text-muted-foreground shadow-sm">일정 후보가 없습니다.</div> : null}
        {status === 'success' ? <StartupResultList results={results} /> : null}
      </div>
    </section>
  );
}

export function WorkspaceHome({
  forcedStartupView,
  mailFolder = 'inbox',
}: {
  forcedStartupView?: WorkspaceStartupView;
  mailFolder?: MailFolder;
} = {}) {
  const [selectedEmail, setSelectedEmail] = useState<number | null>(null);
  const [workspaceActionNotice, setWorkspaceActionNotice] = useState<string | null>(null);
  const [desktopDetailActionCommand, setDesktopDetailActionCommand] = useState<WorkspaceActionCommand | null>(null);
  const [mobileDetailActionCommand, setMobileDetailActionCommand] = useState<MobileActionCommand | null>(null);
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  const [isTabletViewport, setIsTabletViewport] = useState(false);
  const [viewportReady, setViewportReady] = useState(false);
  const [mobileViewportModeVersion, setMobileViewportModeVersion] = useState(0);
  const [desktopViewportModeVersion, setDesktopViewportModeVersion] = useState(0);
  const mobileViewportModeRef = useRef(isMobileViewport);
  const desktopViewportModeRef = useRef(false);
  const storedStartupView = useWorkspaceStartupView();
  const startupView = forcedStartupView ?? storedStartupView;
  const [startupViewOverride, setStartupViewOverride] = useState<WorkspaceStartupView | null>(null);
  const [mobileWorkspaceOverride, setMobileWorkspaceOverride] = useState(false);
  const [mobileWorkspaceOverrideReady, setMobileWorkspaceOverrideReady] = useState(false);
  const activeStartupView = startupViewOverride ?? startupView;
  const showMobileDashboard = activeStartupView === 'dashboard' && mobileWorkspaceOverrideReady && isMobileViewport && !mobileWorkspaceOverride;

  const mobileView = useMobileWorkspaceView();
  const effectiveMobileView = mobileView === 'detail' && selectedEmail === null ? 'inbox' : mobileView;
  const openStartupView = (view: WorkspaceStartupView) => {
    setStartupViewOverride(view);
    setMobileWorkspaceOverride(view !== 'dashboard');
    if (view === 'email') {
      setMobileWorkspaceView('inbox', { updateHash: false });
    }
    if (view === 'calendar') {
      setMobileWorkspaceView('calendar', { updateHash: false });
    }
  };
  const handleSelectEmail = useCallback((emailId: number) => {
    setStartupViewOverride('email');
    setSelectedEmail(emailId);
    setWorkspaceActionNotice(null);
    setDesktopDetailActionCommand(null);
    setMobileDetailActionCommand(null);
    if (typeof window !== 'undefined' && window.matchMedia?.('(max-width: 1023px)').matches) {
      setMobileWorkspaceView('detail');
    }
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia?.('(max-width: 1023px)');
    if (!mediaQuery) {
      const markViewportReady = () => setViewportReady(true);
      markViewportReady();
      return;
    }

    const syncViewport = () => {
      if (mobileViewportModeRef.current !== mediaQuery.matches) {
        mobileViewportModeRef.current = mediaQuery.matches;
        setMobileViewportModeVersion((version) => version + 1);
        setDesktopViewportModeVersion((version) => version + 1);
      }
      setIsMobileViewport(mediaQuery.matches);
      setViewportReady(true);
    };
    syncViewport();
    mediaQuery.addEventListener('change', syncViewport);
    return () => mediaQuery.removeEventListener('change', syncViewport);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia?.('(min-width: 1024px) and (max-width: 1279px)');
    if (!mediaQuery) return;

    const syncViewport = () => {
      if (desktopViewportModeRef.current !== mediaQuery.matches) {
        desktopViewportModeRef.current = mediaQuery.matches;
        setDesktopViewportModeVersion((version) => version + 1);
      }
      setIsTabletViewport(mediaQuery.matches);
    };
    syncViewport();
    mediaQuery.addEventListener('change', syncViewport);
    return () => mediaQuery.removeEventListener('change', syncViewport);
  }, []);

  useEffect(() => {
    if (window.location.hash.startsWith('#mobile-')) {
      return;
    }
    if (startupView === 'calendar') {
      setMobileWorkspaceView('calendar', { updateHash: false });
    }
    if (startupView === 'email') {
      setMobileWorkspaceView('inbox', { updateHash: false });
    }
  }, [startupView]);

  useEffect(() => {
    const clearStartupOverride = () => setStartupViewOverride(null);
    window.addEventListener('naruon:startup-view-change', clearStartupOverride);
    return () => window.removeEventListener('naruon:startup-view-change', clearStartupOverride);
  }, []);

  useEffect(() => {
    const syncMobileWorkspaceOverride = (event?: Event) => {
      const eventView = event instanceof CustomEvent ? (event as CustomEvent<{ view?: string }>).detail?.view : null;
      const hasExplicitWorkspaceOverride = typeof eventView === 'string' && eventView !== 'inbox';
      setMobileWorkspaceOverride(window.location.hash.startsWith('#mobile-') || hasExplicitWorkspaceOverride);
      setMobileWorkspaceOverrideReady(true);
    };
    syncMobileWorkspaceOverride();
    const clearMobileWorkspaceOverride = () => {
      setMobileWorkspaceOverride(false);
      setMobileWorkspaceOverrideReady(true);
    };
    window.addEventListener('hashchange', syncMobileWorkspaceOverride);
    window.addEventListener('naruon:mobile-workspace', syncMobileWorkspaceOverride);
    window.addEventListener('naruon:startup-view-change', clearMobileWorkspaceOverride);
    return () => {
      window.removeEventListener('hashchange', syncMobileWorkspaceOverride);
      window.removeEventListener('naruon:mobile-workspace', syncMobileWorkspaceOverride);
      window.removeEventListener('naruon:startup-view-change', clearMobileWorkspaceOverride);
    };
  }, []);

  useEffect(() => {
    function handleHeaderAction(event: Event) {
      const action = (event as CustomEvent<{ action?: string }>).detail?.action;
      if (!action) return;

      if (selectedEmail === null) {
        setWorkspaceActionNotice('먼저 메일을 선택하세요.');
        return;
      }

      setWorkspaceActionNotice(null);
      if (isMobileViewport) {
        setMobileDetailActionCommand((previous) => ({ id: (previous?.id ?? 0) + 1, action, modeVersion: mobileViewportModeVersion }));
        setMobileWorkspaceView('detail');
      } else {
        setDesktopDetailActionCommand((previous) => ({
          id: (previous?.id ?? 0) + 1,
          action,
          target: isTabletViewport ? 'tablet' : 'desktop',
          modeVersion: desktopViewportModeVersion,
        }));
      }
    }

    window.addEventListener('naruon:header-action', handleHeaderAction);
    return () => window.removeEventListener('naruon:header-action', handleHeaderAction);
  }, [desktopViewportModeVersion, isMobileViewport, isTabletViewport, mobileViewportModeVersion, selectedEmail]);

  return (
    <>
      {workspaceActionNotice && (
        <div role="status" aria-live="polite" className="absolute left-1/2 top-3 z-50 -translate-x-1/2 rounded-2xl border border-primary/20 bg-card px-4 py-3 text-sm font-bold text-primary shadow-lg">
          {workspaceActionNotice}
        </div>
      )}
      {activeStartupView === 'dashboard' && viewportReady && !isMobileViewport && <div className="hidden h-full lg:block"><StartupDashboard onOpenView={openStartupView} /></div>}
      {activeStartupView === 'calendar' && viewportReady && !isMobileViewport && <div className="hidden h-full lg:block"><StartupCalendar onOpenView={openStartupView} /></div>}
      <section role="region" aria-label="데스크톱 메일 작업공간" className={`${activeStartupView === 'email' ? 'hidden xl:block' : 'hidden'} h-full`}>
        {viewportReady && !isMobileViewport && !isTabletViewport ? (
        <ResizablePanelGroup orientation="horizontal" className="h-full items-stretch rounded-3xl border border-border/80 bg-card/70 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur-xl">
          <ResizablePanel defaultSize={27} minSize={22}>
            <EmailList onSelectEmail={handleSelectEmail} selectedEmailId={selectedEmail} folder={mailFolder} />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={48} minSize={34}>
            <EmailDetail emailId={selectedEmail} actionCommand={desktopDetailActionCommand?.target === 'desktop' && desktopDetailActionCommand.modeVersion === desktopViewportModeVersion ? desktopDetailActionCommand : null} />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={25} minSize={20}>
            <div className="h-full flex flex-col bg-gradient-to-b from-primary/5 via-background to-emerald-500/5 p-4">
              <div className="mb-4 rounded-2xl border border-primary/15 bg-card p-4 shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="grid size-9 place-items-center rounded-xl bg-primary/10 text-primary">
                    <Network className="size-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="font-bold text-sm text-foreground">관계 맥락</h3>
                    <p className="text-xs text-muted-foreground">메일과 관계의 흐름을 시각화합니다.</p>
                  </div>
                </div>
              </div>
              <div className="flex-1 overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
                <NetworkGraph />
              </div>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
        ) : null}
      </section>
      <section
        role="region"
        aria-label="태블릿 메일 작업공간"
        className={`${activeStartupView === 'email' ? 'hidden lg:flex xl:hidden' : 'hidden'} h-full min-h-0 gap-3 rounded-3xl border border-border/80 bg-card/70 p-3 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur-xl`}
      >
        {viewportReady && isTabletViewport ? (
          <>
        <div className="min-w-0 basis-[38%] overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
          <EmailList onSelectEmail={handleSelectEmail} selectedEmailId={selectedEmail} folder={mailFolder} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-hidden">
          <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
            <EmailDetail emailId={selectedEmail} actionCommand={desktopDetailActionCommand?.target === 'tablet' && desktopDetailActionCommand.modeVersion === desktopViewportModeVersion ? desktopDetailActionCommand : null} />
          </div>
          <details aria-label="태블릿 관계 맥락" className="shrink-0 rounded-2xl border border-primary/15 bg-gradient-to-r from-primary/5 via-card to-emerald-500/5 shadow-sm">
            <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-black text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
              <span className="flex items-center gap-2">
                <span className="grid size-9 place-items-center rounded-xl bg-primary/10 text-primary">
                  <Network className="size-4" aria-hidden="true" />
                </span>
                태블릿 맥락 패널
              </span>
              <span className="text-xs font-semibold text-muted-foreground">필요할 때 펼치기</span>
            </summary>
            <div className="border-t border-border/70 p-4">
              <p className="mb-3 text-xs font-semibold text-muted-foreground">관계 맥락은 필요할 때 펼쳐서 확인합니다.</p>
              <div className="h-80 overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
                <NetworkGraph />
              </div>
            </div>
          </details>
        </div>
          </>
        ) : null}
      </section>
       {showMobileDashboard && <div className="h-full lg:hidden"><StartupDashboard onOpenView={openStartupView} /></div>}
       <div className={`${showMobileDashboard ? 'hidden' : 'block'} h-full overflow-hidden rounded-3xl border border-border/80 bg-card/70 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur-xl lg:hidden`}>
          <section
            id="mobile-inbox"
            aria-label="모바일 받은편지함"
            role="region"
            className={`mobile-workspace-panel mobile-workspace-panel-inbox h-full ${effectiveMobileView === 'inbox' ? 'block' : 'hidden'}`}
          >
            <EmailList onSelectEmail={handleSelectEmail} selectedEmailId={selectedEmail} folder={mailFolder} />
          </section>
          <section
            id="mobile-detail"
            aria-label="모바일 메일 상세"
            role="region"
            className={`mobile-workspace-panel h-full flex-col ${effectiveMobileView === 'detail' && selectedEmail !== null ? 'flex' : 'hidden'}`}
          >
            <div className="p-3 border-b border-border bg-card">
              <button type="button"
                onClick={() => {
                  setSelectedEmail(null);
                  setMobileDetailActionCommand(null);
                  setMobileWorkspaceView('inbox');
                }}
                className="text-sm font-semibold text-primary flex items-center gap-1"
              >
                ← 목록으로
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              {viewportReady && isMobileViewport && effectiveMobileView === 'detail' && selectedEmail !== null ? <EmailDetail emailId={selectedEmail} actionCommand={mobileDetailActionCommand?.modeVersion === mobileViewportModeVersion ? mobileDetailActionCommand : null} /> : null}
            </div>
          </section>
          <section
            id="mobile-search"
            aria-label="모바일 맥락 검색"
            role="region"
            className={`mobile-workspace-panel mobile-workspace-panel-search h-full ${effectiveMobileView === 'search' ? 'flex' : 'hidden'} flex-col overflow-y-auto bg-gradient-to-b from-primary/5 via-background to-card p-4 pb-[calc(7rem+env(safe-area-inset-bottom))]`}
          >
            {effectiveMobileView === 'search' ? <MobileSearchPanel /> : null}
          </section>
          <section
            id="mobile-actions"
            aria-label="모바일 판단 보조 실행"
            role="region"
            className={`mobile-workspace-panel mobile-workspace-panel-actions h-full ${effectiveMobileView === 'actions' ? 'flex' : 'hidden'} flex-col overflow-y-auto bg-gradient-to-b from-primary/5 via-background to-emerald-500/5 p-4 pb-[calc(7rem+env(safe-area-inset-bottom))]`}
          >
            <div className="mb-4 rounded-2xl border border-primary/15 bg-card p-4 shadow-sm">
              <div className="flex items-center gap-2">
                <span className="grid size-9 place-items-center rounded-xl bg-primary/10 text-primary">
                  <Network className="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 className="font-bold text-sm text-foreground">관계 맥락</h3>
                  <p className="text-xs text-muted-foreground">메일과 관계의 흐름을 시각화합니다.</p>
                </div>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
              {effectiveMobileView === 'actions' && <NetworkGraph />}
            </div>
          </section>
          <section
            id="mobile-calendar"
            aria-label="모바일 일정 연결"
            role="region"
            className={`mobile-workspace-panel mobile-workspace-panel-calendar h-full ${effectiveMobileView === 'calendar' ? 'flex' : 'hidden'} flex-col overflow-y-auto bg-gradient-to-b from-primary/5 via-background to-card p-4 pb-[calc(7rem+env(safe-area-inset-bottom))]`}
          >
            {effectiveMobileView === 'calendar' ? <MobileCalendarPanel /> : null}
          </section>
      </div>
    </>
  );
}

export default WorkspaceHome;
