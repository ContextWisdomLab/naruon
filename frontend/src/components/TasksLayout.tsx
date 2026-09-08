"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Plus, Search, Filter, User, CalendarDays, Inbox, AlertCircle, X } from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { toSafeReactText } from '@/lib/safe-text';

type TicketTask = {
  id: string;
  title: string;
  status: 'open' | 'in_progress' | 'blocked' | 'done';
  priority: 'low' | 'normal' | 'high' | 'urgent';
  source_type: string;
  source_email_id: string | null;
  related_thread_id: string | null;
  updated_at: string;
};

type KnowledgeMaterializationIntent = {
  intent: 'knowledge_materialization';
  status: string;
  task_id: string;
  source_type: 'self_sent_knowledge';
  source_email_id: string | null;
  source_thread_id: string | null;
  source_id: string | null;
  target_label: string | null;
  target_path: string;
  requires_if_match: boolean;
  provenance: string;
  provider_write_executed: boolean;
  audit_event: string;
  runner_request_id?: string | null;
  provider_status?: number | null;
  error_code?: string | null;
  retry_item_uid?: string | null;
};

type KnowledgeIntentEntry = {
  state: 'idle' | 'loading' | 'ready' | 'error';
  result: KnowledgeMaterializationIntent | null;
};

type ReplySlaEscalationResponse = {
  evaluated: number;
  created: number;
  policy: {
    overdue_hours: number;
  };
  tasks: TicketTask[];
};

const taskStatusLabels: Record<TicketTask['status'], string> = {
  open: '접수',
  in_progress: '진행',
  blocked: '차단',
  done: '완료',
};

const taskStatusChangeLabels: Record<TicketTask['status'], string> = {
  open: '접수로',
  in_progress: '진행으로',
  blocked: '차단으로',
  done: '완료로',
};

const ticketStatusOptions: TicketTask['status'][] = ['open', 'in_progress', 'blocked', 'done'];

const taskPriorityLabels: Record<TicketTask['priority'], string> = {
  low: '낮음',
  normal: '보통',
  high: '높음',
  urgent: '긴급',
};

type TicketStatus = 'loading' | 'ready' | 'empty' | 'auth' | 'error';
type ReplySlaStatus = 'idle' | 'loading' | 'ready' | 'error';
type PriorityFilter = 'all' | TicketTask['priority'];

function getApiErrorStatus(error: unknown) {
  const shapedError = error as { status?: unknown; response?: { status?: unknown } } | null;
  if (typeof shapedError?.status === 'number') return shapedError.status;
  if (typeof shapedError?.response?.status === 'number') return shapedError.response.status;
  return null;
}

function safeTaskTitle(title: string) {
  const displayTitle = toSafeReactText(title, '제목 없는 작업')
    .replace(/<[^>]*>/g, ' ')
    .replace(/[<>]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return displayTitle || '제목 없는 작업';
}

function formatTaskTimestamp(value: string | null | undefined) {
  if (!value) return '기록 없음';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '기록 없음';
  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

function getTaskSourceLabel(sourceType: string) {
  switch (sourceType) {
    case 'email':
      return '메일 근거';
    case 'reply_sla':
      return '답장 대기 메일';
    case 'self_sent_knowledge':
      return '나에게 보낸 지식 메일';
    case 'webdav':
      return '문서 원본';
    default:
      return '원본 근거';
  }
}

function getTaskEvidenceLabel(task: TicketTask) {
  if (task.related_thread_id) return '스레드 근거 연결됨';
  if (task.source_email_id) return '메일 근거 연결됨';
  return '원본 연결 대기';
}

function getKnowledgeTargetLabel(intent: KnowledgeMaterializationIntent) {
  return intent.target_label || intent.source_id ? 'WebDAV/Notes 의도 준비' : '대상 원본 확인 필요';
}

function getKnowledgeConflictLabel(intent: KnowledgeMaterializationIntent) {
  return intent.requires_if_match ? '충돌 검사 필요' : '충돌 검사 선택';
}

function getWriteBoundaryLabel(providerWriteExecuted: boolean) {
  return providerWriteExecuted ? '외부 쓰기 실행됨' : '의도만 기록';
}

function getKnowledgeExecutionLabel(intent: KnowledgeMaterializationIntent) {
  if (intent.provider_write_executed) return '외부 쓰기 실행됨';
  if (intent.retry_item_uid || intent.status === 'queued') return '커넥터 실행 요청 접수';
  if (intent.error_code) return '커넥터 실행 실패';
  return getWriteBoundaryLabel(false);
}

function getKnowledgeRetryLabel(intent: KnowledgeMaterializationIntent) {
  if (intent.retry_item_uid || intent.status === 'queued') return '재시도 대기';
  if (intent.provider_write_executed) return '재시도 없음';
  return '실행 요청 없음';
}

const TASK_VIEW_MODES = ['내 작업', '위임한 작업', '칸반', '작업 상세'] as const;
type TaskViewMode = (typeof TASK_VIEW_MODES)[number];

function taskViewTabId(mode: TaskViewMode) {
  return `tasks-view-tab-${TASK_VIEW_MODES.indexOf(mode)}`;
}

export function TasksLayout() {
  const [viewMode, setViewMode] = useState<TaskViewMode>('칸반');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [ticketTasks, setTicketTasks] = useState<TicketTask[]>([]);
  const [ticketStatus, setTicketStatus] = useState<TicketStatus>('loading');
  const [ticketActionStatus, setTicketActionStatus] = useState<string | null>(null);
  const [replySlaStatus, setReplySlaStatus] = useState<ReplySlaStatus>('idle');
  const [knowledgeIntentByTask, setKnowledgeIntentByTask] = useState<Record<string, KnowledgeIntentEntry>>({});
  const [taskSearch, setTaskSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>('all');
  const taskSearchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;

    void apiClient
      .get<TicketTask[]>('/api/tasks')
      .then((apiTasks) => {
        if (cancelled) return;
        setTicketTasks(apiTasks);
        setTicketStatus(apiTasks.length > 0 ? 'ready' : 'empty');
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const status = getApiErrorStatus(error);
        setTicketTasks([]);
        setTicketStatus(status === 401 || status === 403 ? 'auth' : 'error');
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleTicketStatusChange = async (taskId: string, status: TicketTask['status']) => {
    setTicketActionStatus(null);
    try {
      const updatedTask = await apiClient.patch<TicketTask>(`/api/tasks/${encodeURIComponent(taskId)}`, { status });
      setTicketTasks((currentTasks) =>
        currentTasks.map((task) => (task.id === updatedTask.id ? updatedTask : task)),
      );
      setTicketActionStatus(`${safeTaskTitle(updatedTask.title)} 상태를 ${taskStatusChangeLabels[updatedTask.status]} 변경했습니다.`);
    } catch {
      setTicketActionStatus('티켓 상태 변경에 실패했습니다.');
    }
  };

  const handleKnowledgeIntentCreate = async (taskId: string, executeProvider = false) => {
    setKnowledgeIntentByTask((current) => ({
      ...current,
      [taskId]: { state: 'loading', result: null },
    }));
    try {
      const result = await apiClient.post<KnowledgeMaterializationIntent>(
        '/api/webdav/knowledge-materialization-intent',
        {
          source_task_id: taskId,
          ...(executeProvider ? { execute_provider: true } : {}),
        },
      );
      setKnowledgeIntentByTask((current) => ({
        ...current,
        [taskId]: { state: 'ready', result },
      }));
    } catch {
      setKnowledgeIntentByTask((current) => ({
        ...current,
        [taskId]: { state: 'error', result: null },
      }));
    }
  };

  const handleReplySlaEscalation = async () => {
    setReplySlaStatus('loading');
    setTicketActionStatus(null);
    try {
      const result = await apiClient.post<ReplySlaEscalationResponse>(
        '/api/tasks/reply-sla-escalations',
        { overdue_hours: 48 },
      );
      setTicketTasks((currentTasks) => {
        const mergedTasks = new Map(currentTasks.map((task) => [task.id, task]));
        result.tasks.forEach((task) => mergedTasks.set(task.id, task));
        return Array.from(mergedTasks.values());
      });
      if (result.tasks.length > 0) {
        setTicketStatus('ready');
      } else {
        setTicketStatus((currentStatus) => (
          currentStatus === 'loading' || currentStatus === 'error' ? 'empty' : currentStatus
        ));
      }
      setReplySlaStatus('ready');
      setTicketActionStatus(`${result.created}개 미답변 팔로업 작업을 생성했습니다. ${result.evaluated}개 대기 메일을 ${result.policy.overdue_hours}시간 기준으로 확인했습니다.`);
    } catch {
      setReplySlaStatus('error');
      setTicketActionStatus('미답변 팔로업 작업 생성에 실패했습니다.');
    }
  };

  const filteredTicketTasks = useMemo(() => {
    const normalizedQuery = taskSearch.trim().toLowerCase();
    return ticketTasks.filter((task) => {
      if (priorityFilter !== 'all' && task.priority !== priorityFilter) return false;
      if (!normalizedQuery) return true;
      const searchable = `${safeTaskTitle(task.title)} ${getTaskSourceLabel(task.source_type)} ${taskStatusLabels[task.status]} ${taskPriorityLabels[task.priority]}`.toLowerCase();
      return searchable.includes(normalizedQuery);
    });
  }, [priorityFilter, taskSearch, ticketTasks]);

  const liveBoardCounts = useMemo(() => {
    return filteredTicketTasks.reduce<Record<TicketTask['status'], number>>(
      (acc, task) => {
        acc[task.status] += 1;
        return acc;
      },
      { open: 0, in_progress: 0, blocked: 0, done: 0 },
    );
  }, [filteredTicketTasks]);

  const tasksByStatus = useMemo(() => {
    return filteredTicketTasks.reduce<Record<TicketTask['status'], TicketTask[]>>(
      (acc, task) => {
        acc[task.status].push(task);
        return acc;
      },
      { open: [], in_progress: [], blocked: [], done: [] },
    );
  }, [filteredTicketTasks]);

  const currentColumns = useMemo(() => [
    { id: 'open' as const, title: '접수', count: liveBoardCounts.open, color: 'bg-blue-100 text-blue-700' },
    { id: 'in_progress' as const, title: '진행', count: liveBoardCounts.in_progress, color: 'bg-orange-100 text-orange-700' },
    { id: 'blocked' as const, title: '검토 필요', count: liveBoardCounts.blocked, color: 'bg-red-100 text-red-700' },
    { id: 'done' as const, title: '완료', count: liveBoardCounts.done, color: 'bg-green-100 text-green-700' },
  ], [liveBoardCounts.blocked, liveBoardCounts.done, liveBoardCounts.in_progress, liveBoardCounts.open]);

  const selectedTask = useMemo(
    () => ticketTasks.find((task) => task.id === selectedTaskId) ?? null,
    [selectedTaskId, ticketTasks],
  );

  const selfSentKnowledgeTasks = useMemo(
    () => ticketTasks.filter((task) => task.source_type === 'self_sent_knowledge'),
    [ticketTasks],
  );

  // ⚡ Bolt: Wrap Kanban columns in useMemo to prevent O(N) re-renders
  // 🎯 Why: Mapping over potentially large lists of tasks by status blocks the main thread during unrelated state updates.
  const kanbanBoard = useMemo(() => (
    <div className="flex min-h-[560px] gap-6">
      {currentColumns.map((col) => (
        <div
          key={col.id}
          className="flex h-full w-80 flex-col rounded-xl bg-card border border-border shadow-sm shrink-0"
        >
          <div className="flex items-center justify-between border-b border-border p-4">
            <div className="flex items-center gap-2">
              <h2 className="font-bold text-sm">{col.title}</h2>
              <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${col.color}`}>{col.count}</span>
            </div>
            <span aria-label={`${col.title} 원본 작업 수`} className="text-xs font-bold text-muted-foreground">{col.count}건</span>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {tasksByStatus[col.id].length > 0 ? tasksByStatus[col.id].map((task) => (
              <button
                key={task.id}
                type="button"
                onClick={() => { setSelectedTaskId(task.id); setViewMode('작업 상세'); }}
                className="w-full rounded-lg border border-border bg-background p-3 text-left shadow-sm transition-all hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              >
                <div className="flex flex-wrap gap-1 mb-2">
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-bold text-primary">{getTaskSourceLabel(task.source_type)}</span>
                  <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-bold text-secondary-foreground">{taskPriorityLabels[task.priority]}</span>
                </div>
                <h3 className="font-bold text-sm text-foreground leading-snug">{safeTaskTitle(task.title)}</h3>
                <div className="mt-3 flex items-center justify-between text-xs font-semibold text-muted-foreground">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1" title="업데이트">
                      <CalendarDays className="size-3.5" />
                      <span>{formatTaskTimestamp(task.updated_at)}</span>
                    </div>
                    <div className="flex items-center gap-1" title="작업 출처">
                      {task.status === 'blocked' ? <AlertCircle className="size-3.5" /> : <Inbox className="size-3.5" />}
                      <span>{getTaskEvidenceLabel(task)}</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-center size-6 rounded-full bg-primary/10 text-primary" title="서명 세션 작업">
                    <User className="size-3.5" />
                  </div>
                </div>
              </button>
            )) : (
              <p className="rounded-lg border border-dashed border-border p-3 text-sm font-semibold text-muted-foreground">
                {taskSearch || priorityFilter !== 'all' ? '필터에 맞는 작업이 없습니다.' : '이 상태의 연결 작업이 없습니다.'}
              </p>
            )}
          </div>
          <div className="p-3 border-t border-border">
            <a href="/mail" className="flex w-full items-center justify-center gap-2 rounded-md py-1.5 text-sm font-semibold text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
              <Plus className="size-4" /> 관련 메일에서 생성
            </a>
          </div>
        </div>
      ))}
    </div>
  ), [currentColumns, tasksByStatus, taskSearch, priorityFilter, setSelectedTaskId, setViewMode]);


  // ⚡ Bolt: Wrap My Tasks list in useMemo to prevent O(N) re-renders
  // 🎯 Why: Mapping over potentially large lists of filtered tasks blocks the main thread during unrelated state updates.
  const myTasksList = useMemo(() => {
    if (viewMode !== '내 작업') return null;
    return filteredTicketTasks.length > 0 ? filteredTicketTasks.map(task => (
      <button key={task.id} type="button" className="flex w-full items-center justify-between p-4 rounded-xl border border-border bg-card text-left shadow-sm transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40" onClick={() => { setSelectedTaskId(task.id); setViewMode('작업 상세'); }}>
        <div className="flex items-center gap-4">
          <div className={`size-3 rounded-full ${task.priority === 'urgent' ? 'bg-red-500' : task.priority === 'high' ? 'bg-orange-500' : 'bg-blue-500'}`}></div>
          <div>
            <h3 className="font-bold text-sm">{safeTaskTitle(task.title)}</h3>
            <p className="text-xs text-muted-foreground mt-1">근거: {getTaskEvidenceLabel(task)} | 원본: {getTaskSourceLabel(task.source_type)}</p>
          </div>
        </div>
        <span className={`px-2 py-1 rounded-full text-xs font-bold ${task.status === 'done' ? 'bg-green-100 text-green-700' : 'bg-secondary text-secondary-foreground'}`}>{taskStatusLabels[task.status]}</span>
      </button>
    )) : (
      <p className="rounded-xl border border-dashed border-border bg-card p-4 text-sm font-semibold text-muted-foreground">서명 세션에 연결된 내 작업이 없습니다.</p>
    );
  }, [filteredTicketTasks, setSelectedTaskId, setViewMode, viewMode]);
  const handleViewModeKeyDown = (event: KeyboardEvent<HTMLButtonElement>, mode: TaskViewMode) => {

    const currentIndex = TASK_VIEW_MODES.indexOf(mode);
    const lastIndex = TASK_VIEW_MODES.length - 1;
    let nextIndex: number;
    if (event.key === 'ArrowRight') nextIndex = currentIndex === lastIndex ? 0 : currentIndex + 1;
    else if (event.key === 'ArrowLeft') nextIndex = currentIndex === 0 ? lastIndex : currentIndex - 1;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = lastIndex;
    else return;
    event.preventDefault();
    const nextMode = TASK_VIEW_MODES[nextIndex];
    setViewMode(nextMode);
    document.getElementById(taskViewTabId(nextMode))?.focus();
  };

  return (
    <div className="flex h-full min-h-0 bg-background text-foreground flex-col">
      {/* Top Header */}
      <header className="flex shrink-0 flex-col gap-3 border-b border-border bg-card px-4 py-3 lg:h-16 lg:flex-row lg:items-center lg:justify-between lg:px-6 lg:py-0">
        <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center lg:gap-6">
          <h1 className="text-xl font-bold">실행 항목 추적</h1>
          <p className="sr-only">리소스 배정 검토 회의</p>
          <div role="tablist" aria-label="작업 보기 방식" className="flex max-w-full overflow-x-auto rounded-md border border-border">
            {TASK_VIEW_MODES.map((mode) => (
              <button type="button"
                key={mode}
                id={taskViewTabId(mode)}
                role="tab"
                aria-selected={viewMode === mode}
                tabIndex={viewMode === mode ? 0 : -1}
                onClick={() => setViewMode(mode)}
                onKeyDown={(event) => handleViewModeKeyDown(event, mode)}
                className={`shrink-0 px-4 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-1 focus-visible:ring-offset-background ${viewMode === mode ? 'bg-primary text-primary-foreground' : 'bg-background hover:bg-secondary'}`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:gap-3">
          <div className="relative min-w-[180px] flex-1 sm:flex-none">
            <label htmlFor="task-search-input" className="sr-only">작업 맥락 검색</label>
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" aria-hidden="true" />
            <input
              ref={taskSearchInputRef}
              id="task-search-input"
              type="search"
              inputMode="search"
              role="searchbox"
              value={taskSearch}
              onChange={(event) => setTaskSearch(event.target.value)}
              placeholder="작업 맥락 검색..."
              aria-label="작업 맥락 검색"
              className="h-9 w-full rounded-md border border-border bg-background pl-9 pr-9 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary sm:w-64 [&::-webkit-search-cancel-button]:hidden"
            />
            {taskSearch.length > 0 && (
              <button
                type="button"
                aria-label="맥락 검색어 지우기"
                onClick={() => {
                  setTaskSearch("");
                  taskSearchInputRef.current?.focus();
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            )}
          </div>
          <label className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-1.5 text-sm font-semibold">
            <Filter className="size-4" />
            <span className="sr-only">우선순위 필터</span>
            <select
              value={priorityFilter}
              onChange={(event) => setPriorityFilter(event.target.value as PriorityFilter)}
              className="bg-transparent text-sm font-semibold outline-none"
            >
              <option value="all">전체</option>
              <option value="urgent">긴급</option>
              <option value="high">높음</option>
              <option value="normal">보통</option>
              <option value="low">낮음</option>
            </select>
          </label>
          <a href="/mail" className="flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm font-bold text-primary-foreground hover:bg-primary/90">
            <Plus className="size-4" /> 메일에서 작업 생성
          </a>
        </div>
      </header>

      {/* Kanban Board Area */}
      <main className="flex-1 overflow-x-auto overflow-y-auto bg-secondary/20 px-4 py-4 pb-28 sm:p-6">
        <section aria-label="원본 연결 티켓 상태 보드" className="mb-6 rounded-xl border border-border bg-card p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-bold">실제 티켓 큐</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                서명 세션의 작업 API에서 원본 메일, 스레드, 상태와 우선순위를 읽어 티켓 보드와 함께 추적합니다.
              </p>
            </div>
            <div role="status" aria-live="polite" className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
              {ticketStatus === 'loading' ? '작업 불러오는 중' : null}
              {ticketStatus === 'ready' ? `${ticketTasks.length}개 티켓 연결` : null}
              {ticketStatus === 'empty' ? '연결된 티켓 없음' : null}
              {ticketStatus === 'auth' ? '인증된 세션 필요' : null}
              {ticketStatus === 'error' ? '작업 API 오류' : null}
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-4">
            {(Object.keys(taskStatusLabels) as TicketTask['status'][]).map((status) => (
              <div key={status} className="rounded-lg border border-border bg-background/70 p-3">
                <p className="text-xs font-bold text-muted-foreground">{taskStatusLabels[status]}</p>
                <p className="mt-1 text-xl font-bold text-foreground">{liveBoardCounts[status]}</p>
              </div>
            ))}
          </div>

          <section aria-label="기한 지난 답변 팔로업" className="mt-4 border-t border-border pt-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-foreground">기한 지난 답변 처리</h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  48시간 넘게 답변이 없는 보낸 메일을 원본 메일과 스레드가 연결된 티켓으로 올립니다.
                </p>
              </div>
              <button
                type="button"
                aria-label="보낸 메일 미답변 팔로업 작업 생성"
                disabled={replySlaStatus === 'loading'}
                aria-busy={replySlaStatus === 'loading'}
                onClick={() => void handleReplySlaEscalation()}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:bg-primary/90 disabled:cursor-wait disabled:opacity-70"
              >
                <Plus className="size-3.5" />
                {replySlaStatus === 'loading' ? '확인 중' : '팔로업 작업 생성'}
              </button>
            </div>
            {replySlaStatus === 'ready' ? (
              <p role="status" className="mt-3 text-xs font-semibold text-muted-foreground">
                미답변 팔로업 결과가 보드에 반영되었습니다.
              </p>
            ) : null}
            {replySlaStatus === 'error' ? (
              <p role="status" className="mt-3 text-xs font-semibold text-red-700">
                미답변 팔로업 작업 생성을 완료하지 못했습니다.
              </p>
            ) : null}
          </section>

          {ticketStatus === 'ready' ? (
            <div aria-label="원본 연결 티켓 목록" className="mt-4 grid gap-3 lg:grid-cols-2">
              {filteredTicketTasks.slice(0, 4).map((task) => {
                const displayTitle = safeTaskTitle(task.title);
                return (
                  <article key={task.id} className="rounded-lg border border-border bg-background/75 p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-bold text-foreground">{displayTitle}</h3>
                      <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">
                        {taskStatusLabels[task.status]} · {taskPriorityLabels[task.priority]}
                      </span>
                    </div>
                    <dl className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                      <div>
                        <dt className="font-bold text-foreground">원본</dt>
                        <dd>{getTaskSourceLabel(task.source_type)}</dd>
                      </div>
                      <div>
                        <dt className="font-bold text-foreground">근거</dt>
                        <dd>{getTaskEvidenceLabel(task)}</dd>
                      </div>
                      <div>
                        <dt className="font-bold text-foreground">업데이트</dt>
                        <dd>{formatTaskTimestamp(task.updated_at)}</dd>
                      </div>
                    </dl>
                    <div className="mt-3 flex flex-wrap gap-2" aria-label={`${displayTitle} 상태 변경`}>
                      {ticketStatusOptions.map((status) => (
                        <button
                          key={status}
                          type="button"
                          aria-label={`${displayTitle} 상태를 ${taskStatusChangeLabels[status]} 변경`}
                          aria-pressed={task.status === status}
                          onClick={() => void handleTicketStatusChange(task.id, status)}
                          className={`rounded-md border px-2.5 py-1 text-xs font-bold transition-colors ${
                            task.status === status
                              ? 'border-primary bg-primary text-primary-foreground'
                              : 'border-border bg-card text-foreground hover:border-primary/60 hover:bg-secondary'
                          }`}
                        >
                          {taskStatusLabels[status]}
                        </button>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : null}

          {ticketStatus === 'ready' && selfSentKnowledgeTasks.length > 0 ? (
            <section aria-label="나에게 보낸 지식 메일 WebDAV 의도" className="mt-4 border-t border-border pt-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-foreground">나에게 보낸 지식 노트</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    나에게 보낸 지식 메일 작업은 고객 WebDAV/Notes 의도로 준비하고, 사용자가 명시적으로 요청한 경우에만 커넥터 실행을 요청합니다.
                  </p>
                </div>
                <span className="rounded-full bg-secondary px-3 py-1 text-xs font-bold text-secondary-foreground">
                  {selfSentKnowledgeTasks.length}개 지식 작업
                </span>
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                {selfSentKnowledgeTasks.map((task) => {
                  const currentKnowledgeIntent = knowledgeIntentByTask[task.id] ?? {
                    state: 'idle',
                    result: null,
                  };
                  const currentIntent = currentKnowledgeIntent.result;
                  const displayTitle = safeTaskTitle(task.title);
                  return (
                    <article key={task.id} className="rounded-lg border border-border bg-background/75 p-3 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <h4 className="font-bold text-foreground">{displayTitle}</h4>
                          <p className="mt-1 text-xs text-muted-foreground">{getTaskEvidenceLabel(task)}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            aria-label={`${displayTitle} WebDAV 지식 노트 의도 생성`}
                            disabled={currentKnowledgeIntent.state === 'loading'}
                            aria-busy={currentKnowledgeIntent.state === 'loading'}
                            onClick={() => void handleKnowledgeIntentCreate(task.id)}
                            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:bg-primary/90 disabled:cursor-wait disabled:opacity-70"
                          >
                            <Plus className="size-3.5" />
                            {currentKnowledgeIntent.state === 'loading' ? '생성 중' : '의도 생성'}
                          </button>
                          <button
                            type="button"
                            aria-label={`${displayTitle} WebDAV 지식 노트 실행 요청`}
                            disabled={currentKnowledgeIntent.state === 'loading'}
                            aria-busy={currentKnowledgeIntent.state === 'loading'}
                            onClick={() => void handleKnowledgeIntentCreate(task.id, true)}
                            className="rounded-md border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs font-bold text-primary hover:bg-primary/15 disabled:cursor-wait disabled:opacity-70"
                          >
                            실행 요청
                          </button>
                        </div>
                      </div>
                      {currentKnowledgeIntent.state === 'error' ? (
                        <p role="status" className="mt-3 rounded-md border border-red-300 bg-red-50 p-2 text-xs font-semibold text-red-900">
                          WebDAV/Notes 의도를 만들지 못했습니다.
                        </p>
                      ) : null}
                      {currentIntent ? (
                        <dl className="mt-3 grid gap-2 rounded-md border border-border bg-card p-3 text-xs sm:grid-cols-2">
                          <div>
                            <dt className="font-bold text-foreground">목표 저장소</dt>
                            <dd className="text-muted-foreground">{getKnowledgeTargetLabel(currentIntent)}</dd>
                          </div>
                          <div>
                            <dt className="font-bold text-foreground">쓰기 경계</dt>
                            <dd className="text-muted-foreground">{getKnowledgeExecutionLabel(currentIntent)}</dd>
                          </div>
                          <div>
                            <dt className="font-bold text-foreground">충돌 정책</dt>
                            <dd className="text-muted-foreground">{getKnowledgeConflictLabel(currentIntent)}</dd>
                          </div>
                          <div>
                            <dt className="font-bold text-foreground">감사 근거</dt>
                            <dd className="text-muted-foreground">기록됨</dd>
                          </div>
                          <div>
                            <dt className="font-bold text-foreground">재시도 상태</dt>
                            <dd className="text-muted-foreground">{getKnowledgeRetryLabel(currentIntent)}</dd>
                          </div>
                        </dl>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            </section>
          ) : null}

          {ticketActionStatus ? (
            <p role="status" aria-live="polite" className="mt-3 rounded-lg border border-border bg-background/70 p-3 text-sm font-semibold text-foreground">
              {ticketActionStatus}
            </p>
          ) : null}

          {ticketStatus === 'empty' ? (
            <p className="mt-4 rounded-lg border border-dashed border-border bg-background/70 p-3 text-sm text-muted-foreground">
              메일 상세에서 실행 항목을 만들면 원본 연결 티켓으로 표시됩니다.
            </p>
          ) : null}

          {ticketStatus === 'auth' ? (
            <p className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900">
              작업 API는 서명 세션이 있을 때만 읽습니다. 공개 identity header는 사용하지 않습니다.
            </p>
          ) : null}

          {ticketStatus === 'error' ? (
            <p className="mt-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm font-semibold text-red-900">
              작업 API를 불러오지 못했습니다. 서버 상태를 확인한 뒤 다시 시도합니다.
            </p>
          ) : null}
        </section>

        {viewMode === '칸반' && kanbanBoard}
        {viewMode === '내 작업' && (
          <div className="space-y-4 max-w-4xl mx-auto">
            <h2 className="font-bold text-lg mb-4">내 작업</h2>
            {myTasksList}
          </div>
        )}

        {viewMode === '위임한 작업' && (
          <div className="space-y-4 max-w-4xl mx-auto">
            <h2 className="font-bold text-lg mb-4">위임한 작업</h2>
            <div className="rounded-xl border border-dashed border-border bg-card p-5">
              <h3 className="font-bold text-base">위임 근거 연결 대기</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                현재 작업 API는 담당자/위임자 필드를 반환하지 않습니다. 위임 정보가 서버에서 원본 근거로 제공되면 이 목록에 표시합니다.
              </p>
              <a href="/search" className="mt-4 inline-flex rounded-md bg-primary px-3 py-1.5 text-sm font-bold text-primary-foreground hover:bg-primary/90">
                관련 메일 찾기
              </a>
            </div>
          </div>
        )}

        {viewMode === '작업 상세' && (() => {
          const task = selectedTask;
          if (!task) return <div className="p-6 text-center text-muted-foreground">작업을 선택해주세요.</div>;
          
          const priorityText = task.priority === 'urgent' ? '긴급' : task.priority === 'high' ? '우선순위 높음' : task.priority === 'normal' ? '보통' : '낮음';
          const priorityColor = task.priority === 'urgent' ? 'text-red-500 bg-red-100' : task.priority === 'high' ? 'text-orange-500 bg-orange-100' : 'text-blue-500 bg-blue-100';

          return (
          <div className="max-w-4xl mx-auto bg-card border border-border rounded-2xl shadow-sm p-6">
            <div className="flex items-center justify-between border-b border-border pb-4 mb-4">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-bold text-primary bg-primary/10 px-2 py-0.5 rounded">공개 작업</span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${priorityColor}`}>{priorityText}</span>
                </div>
                <h2 className="text-2xl font-bold">{safeTaskTitle(task.title)}</h2>
              </div>
              <a href="/mail" className="px-4 py-2 bg-primary text-primary-foreground text-sm font-bold rounded-lg hover:bg-primary/90">관련 메일 열기</a>
            </div>
            
            <div className="grid grid-cols-3 gap-6 mb-6">
              <div>
                <p className="text-xs text-muted-foreground font-semibold mb-1">담당자</p>
                <div className="flex items-center gap-2">
                  <div className="size-6 rounded-full bg-primary/10 text-primary grid place-items-center"><User className="size-3" /></div>
                  <span className="text-sm font-bold">서명 세션 사용자</span>
                </div>
              </div>
              <div>
                <p className="text-xs text-muted-foreground font-semibold mb-1">최근 업데이트</p>
                <div className="flex items-center gap-2 text-sm font-bold">
                  <CalendarDays className="size-4" /> {formatTaskTimestamp(task.updated_at)}
                </div>
              </div>
              <div>
                <p className="text-xs text-muted-foreground font-semibold mb-1">출처</p>
                <div className="flex items-center gap-2 text-sm font-bold">
                  <Inbox className="size-4" /> {getTaskSourceLabel(task.source_type)}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="font-bold text-base">작업 설명</h3>
              <div className="p-4 bg-secondary/30 rounded-xl text-sm leading-relaxed border border-border/50">
                {getTaskEvidenceLabel(task)} 작업입니다. 상태와 우선순위는 작업 API에 기록된 공개 작업 식별자로만 갱신합니다.
              </div>
              <div className="flex flex-wrap gap-2" aria-label={`${safeTaskTitle(task.title)} 상세 상태 변경`}>
                {ticketStatusOptions.map((status) => (
                  <button
                    key={status}
                    type="button"
                    aria-label={`${safeTaskTitle(task.title)} 상세 상태를 ${taskStatusChangeLabels[status]} 변경`}
                    aria-pressed={task.status === status}
                    onClick={() => void handleTicketStatusChange(task.id, status)}
                    className={`rounded-md border px-3 py-1.5 text-xs font-bold transition-colors ${
                      task.status === status
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border bg-card text-foreground hover:border-primary/60 hover:bg-secondary'
                    }`}
                  >
                    {taskStatusLabels[status]}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-8 pt-6 border-t border-border">
              <h3 className="font-bold text-base mb-4">활동 기록</h3>
              <div className="space-y-4">
                <div className="flex gap-3">
                  <div className="size-8 rounded-full bg-primary/10 text-primary grid place-items-center shrink-0 text-xs font-bold">시</div>
                  <div className="flex-1 bg-secondary/30 rounded-xl p-3 border border-border/50">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold">시스템</span>
                      <span className="text-xs text-muted-foreground">방금 전</span>
                    </div>
                    <p className="text-sm">작업 원본 근거가 연결되었습니다.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );})()}
      </main>
    </div>
  );
}
