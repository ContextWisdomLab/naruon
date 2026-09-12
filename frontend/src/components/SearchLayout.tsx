"use client";

import type { FormEvent } from "react";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  Clock,
  CornerDownRight,
  FileText,
  Loader2,
  Mail,
  Network,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";

import { apiClient } from "@/lib/api-client";
import { isMailListItem } from '@/lib/mail-response';
import {
  bucketSearchRank,
  bucketTextLength,
  createProductEventId,
  recordProductEvent,
} from "@/lib/product-events";

const NetworkGraph = dynamic(() => import("@/components/NetworkGraph"), {
  ssr: false,
});

const DEFAULT_QUERY = "런칭 캠페인";

type SearchResultItem = {
  id: number;
  source_message_id?: string | null;
  subject: string | null;
  sender: string;
  date: string;
  snippet: string;
  thread_id: string | null;
  reply_count?: number;
  score?: number;
  result_kind?: string | null;
  evidence_kinds?: string[];
};

const EVIDENCE_KIND_LABELS: Record<string, string> = {
  email_body: "본문",
  attachment_content: "첨부",
  content_segment: "문서 구절",
  project_graph_object: "프로젝트 항목",
};

function evidenceKindLabel(kind: string | null | undefined) {
  if (!kind || kind === "email_body") return null;
  return EVIDENCE_KIND_LABELS[kind] ?? kind;
}

type SearchResponse = {
  results: SearchResultItem[];
};

type AnswerCitation = {
  email_id: number;
  subject: string | null;
  sender: string | null;
  snippet: string;
};

type AnswerResponse = {
  answer: string | null;
  citations: AnswerCitation[];
  provenance: string | null;
};

type AnswerState =
  | { status: "idle" | "hidden" }
  | { status: "done"; answer: string; citations: AnswerCitation[]; provenance: string | null };

type SenderRelationship = {
  sender_email: string;
  parent_sender_email: string | null;
  source_message_id: string | null;
  source_thread_id: string | null;
  relationship_type: string;
  confidence_score: number;
  next_action: string;
  action_reason: string;
};

type RelationshipState = {
  sourceKey: string | null;
  items: SenderRelationship[];
  error: string | null;
};

type ResultFilter = "all" | "thread" | "single";
type CaptureStatus = "idle" | "loading" | "success" | "error";
type DetailTab = "context" | "source" | "assist";

const resultFilters: { key: ResultFilter; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "thread", label: "스레드" },
  { key: "single", label: "단건" },
];

const detailTabs: { key: DetailTab; label: string }[] = [
  { key: "context", label: "맥락 정보" },
  { key: "source", label: "관계 원본" },
  { key: "assist", label: "판단 보조" },
];

function formatResultDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;

  return new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function resultTitle(result: SearchResultItem) {
  return result.subject?.trim() || "(제목 없음)";
}

function confidencePercent(score: number | undefined) {
  if (typeof score !== "number" || !Number.isFinite(score)) return null;
  const normalized = score <= 1 ? score * 100 : score;
  return Math.max(0, Math.min(100, Math.round(normalized)));
}

function confidenceTone(percent: number | null) {
  if (percent === null) return "border-slate-200 bg-slate-50 text-slate-600";
  if (percent >= 90) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (percent >= 75) return "border-blue-200 bg-blue-50 text-blue-700";
  if (percent >= 60) return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-red-200 bg-red-50 text-red-700";
}

function confidenceLabel(percent: number | null) {
  return percent === null ? "신뢰도 미제공" : `신뢰도 ${percent}%`;
}

function nowMs() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function ontologySourceKey(result: SearchResultItem | null) {
  if (!result) return null;
  return `${result.id}:${result.source_message_id ?? ""}:${result.thread_id ?? ""}`;
}

function buildOntologyUrl(result: SearchResultItem) {
  const params = new URLSearchParams();
  if (result.source_message_id)
    params.set("source_message_id", result.source_message_id);
  if (result.thread_id) params.set("source_thread_id", result.thread_id);
  const query = params.toString();
  return query
    ? `/api/ontology/relationships?${query}`
    : "/api/ontology/relationships";
}

function SenderDagPanel({
  relationships,
  loading,
  error,
  canCapture,
  captureStatus,
  onCapture,
}: {
  relationships: SenderRelationship[];
  loading: boolean;
  error: string | null;
  canCapture: boolean;
  captureStatus: CaptureStatus;
  onCapture: () => void;
}) {
  if (loading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="rounded-lg border border-border bg-background p-4 text-sm font-semibold text-muted-foreground"
      >
        발신자 DAG를 불러오는 중입니다.
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm font-semibold text-destructive"
      >
        {error}
      </div>
    );
  }

  if (relationships.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-background p-4 text-sm font-semibold text-muted-foreground">
        <p>이 맥락 검색 결과에 연결된 발신자 관계가 아직 없습니다.</p>
        {canCapture ? (
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs">
              원본 메일의 sender/thread 근거로 관계와 다음 액션을 캡처합니다.
            </p>
            <button
              type="button"
              onClick={onCapture}
              disabled={captureStatus === "loading"}
              aria-busy={captureStatus === "loading"}
              className="w-full rounded-lg bg-primary px-3 py-2 text-xs font-bold text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:cursor-wait disabled:opacity-60 sm:w-auto inline-flex items-center justify-center"
            >
              {captureStatus === "loading" && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {captureStatus === "loading" ? "캡처 중" : "발신자 관계 캡처"}
            </button>
          </div>
        ) : null}
        {captureStatus === "error" ? (
          <p className="mt-2 text-xs font-bold text-destructive">
            발신자 관계 캡처에 실패했습니다.
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {relationships.map((relationship) => (
        <article
          key={`${relationship.sender_email}:${relationship.source_message_id ?? "global"}:${relationship.source_thread_id ?? "none"}`}
          className="rounded-lg border border-border bg-background p-4"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className="truncate text-sm font-black text-foreground">
                {relationship.sender_email}
              </p>
              <p className="mt-1 text-xs font-semibold text-muted-foreground">
                상위 맥락:{" "}
                {relationship.parent_sender_email ?? "사용자 직접 관계"}
              </p>
            </div>
            <div className="shrink-0 rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
              {relationship.relationship_type} ·{" "}
              {(relationship.confidence_score * 100).toFixed(0)}%
            </div>
          </div>
          <div className="mt-4 grid gap-2 text-xs font-semibold text-muted-foreground sm:grid-cols-2">
            <div className="rounded border border-border bg-card px-3 py-2">
              <p className="break-all text-foreground">
                {relationship.next_action}
              </p>
              <p className="mt-1">Agent next action</p>
            </div>
            <div className="rounded border border-border bg-card px-3 py-2">
              <p className="break-words text-foreground">
                {relationship.action_reason}
              </p>
              <p className="mt-1">판단 근거</p>
            </div>
          </div>
          <p className="mt-3 break-words rounded bg-secondary/40 px-3 py-2 text-[11px] font-semibold text-muted-foreground">
            source={relationship.source_message_id ?? "global"} / thread=
            {relationship.source_thread_id ?? "none"}
          </p>
        </article>
      ))}
    </div>
  );
}

const SearchResultItemComponent = memo(function SearchResultItemComponent({
  result,
  isActive,
  confidence,
  onSelect,
}: {
  result: SearchResultItem;
  isActive: boolean;
  confidence: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(result.id)}
      aria-current={isActive ? "true" : undefined}
      className={`w-full border-l-4 p-4 text-left transition-colors focus-visible:border-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
        isActive
          ? "border-primary bg-secondary/50"
          : "border-transparent hover:bg-secondary/20"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-1 rounded-lg border border-border bg-background p-2">
          <Mail className="size-4 text-primary" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-bold">{resultTitle(result)}</h3>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {result.sender}
          </p>
          <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
            {result.snippet}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded bg-border/50 px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
              <FileText className="size-3" aria-hidden="true" />
              {result.thread_id ? "메일 스레드" : "메일"}
            </span>
            <span className="text-[10px] text-muted-foreground">
              <Clock className="mr-0.5 inline size-3" aria-hidden="true" />
              {formatResultDate(result.date)}
            </span>
            <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-bold text-primary">
              답장 {result.reply_count ?? 1}건
            </span>
            {evidenceKindLabel(result.result_kind) ? (
              <span className="rounded border border-border px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
                근거: {evidenceKindLabel(result.result_kind)}
              </span>
            ) : null}
            <span
              className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${confidenceTone(confidence)}`}
            >
              {confidenceLabel(confidence)}
            </span>
          </div>
        </div>
      </div>
    </button>
  );
});

export function SearchLayout() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchSessionIdRef = useRef(
    createProductEventId("context_search_session"),
  );
  const lastOpenedResultKeyRef = useRef<string | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState(DEFAULT_QUERY);
  const [activeFilter, setActiveFilter] = useState<ResultFilter>("all");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [activeResultId, setActiveResultId] = useState<number | null>(null);
  const [relationshipState, setRelationshipState] = useState<RelationshipState>(
    {
      sourceKey: null,
      items: [],
      error: null,
    },
  );
  const [captureState, setCaptureState] = useState<{
    sourceKey: string | null;
    status: CaptureStatus;
  }>({ sourceKey: null, status: "idle" });
  const [activeDetailTab, setActiveDetailTab] =
    useState<DetailTab>("context");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [answerState, setAnswerState] = useState<AnswerState>({
    status: "idle",
  });

  useEffect(() => {
    const trimmedQuery = submittedQuery.trim();
    const controller = new AbortController();

    if (!trimmedQuery) return () => controller.abort();

    const startedAt = nowMs();
    apiClient
      .post<SearchResponse>(
        "/api/search",
        { query: trimmedQuery, limit: 8 },
        { signal: controller.signal },
      )
      .then((response) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(response.results) || !response.results.every(isMailListItem)) throw new Error('Invalid search response');
        setResults(response.results);
        setActiveResultId(response.results[0]?.id ?? null);
        recordProductEvent("latency_guardrail_recorded", {
          surface: "context_search",
          request_trace_id: createProductEventId("search_trace"),
          operation: "search",
          duration_ms: Math.round(nowMs() - startedAt),
          status: "success",
        });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setResults([]);
        setActiveResultId(null);
        setError("맥락 검색 결과를 불러오지 못했습니다.");
        recordProductEvent("latency_guardrail_recorded", {
          surface: "context_search",
          request_trace_id: createProductEventId("search_trace"),
          operation: "search",
          duration_ms: Math.round(nowMs() - startedAt),
          status: "error",
        });
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [submittedQuery]);

  useEffect(() => {
    const trimmedQuery = submittedQuery.trim();
    const controller = new AbortController();
    if (!trimmedQuery) return () => controller.abort();

    apiClient
      .post<AnswerResponse>(
        "/api/search/answer",
        { query: trimmedQuery, limit: 5 },
        { signal: controller.signal },
      )
      .then((response) => {
        if (controller.signal.aborted) return;
        if (!response.answer) {
          setAnswerState({ status: "hidden" });
          return;
        }
        setAnswerState({
          status: "done",
          answer: response.answer,
          citations: response.citations ?? [],
          provenance: response.provenance,
        });
      })
      .catch(() => {
        // The grounded answer is an enhancement: search must not degrade
        // when the endpoint is unavailable, so the card simply hides.
        if (!controller.signal.aborted) setAnswerState({ status: "hidden" });
      });

    return () => controller.abort();
  }, [submittedQuery]);

  const filteredResults = useMemo(() => {
    if (activeFilter === "thread")
      return results.filter((result) => (result.reply_count ?? 1) > 1);
    if (activeFilter === "single")
      return results.filter((result) => (result.reply_count ?? 1) <= 1);
    return results;
  }, [activeFilter, results]);

  const activeResult =
    filteredResults.find((result) => result.id === activeResultId) ??
    filteredResults[0] ??
    null;
  const activeOntologySourceKey = ontologySourceKey(activeResult);
  const activeOntologyUrl = activeResult
    ? buildOntologyUrl(activeResult)
    : null;
  const relationshipsLoading = Boolean(
    activeOntologySourceKey &&
    relationshipState.sourceKey !== activeOntologySourceKey,
  );
  const relationships = relationshipsLoading ? [] : relationshipState.items;
  const relationshipError = relationshipsLoading
    ? null
    : relationshipState.error;
  const captureStatus =
    captureState.sourceKey === activeOntologySourceKey
      ? captureState.status
      : "idle";
  const canCaptureRelationship = Boolean(
    activeResult?.source_message_id &&
    activeOntologySourceKey &&
    !relationshipsLoading &&
    !relationshipError &&
    relationships.length === 0,
  );
  const activeConfidence = confidencePercent(activeResult?.score);

  useEffect(() => {
    if (!activeResult || loading) return;

    const resultIndex = filteredResults.findIndex((result) => result.id === activeResult.id);
    const eventKey = `${searchSessionIdRef.current}:${activeResult.id}`;
    if (lastOpenedResultKeyRef.current === eventKey) return;
    lastOpenedResultKeyRef.current = eventKey;

    recordProductEvent("context_search_result_opened", {
      surface: "context_search",
      search_session_id: searchSessionIdRef.current,
      result_id: activeResult.id,
      result_type: "mail",
      rank_bucket: bucketSearchRank(resultIndex < 0 ? 0 : resultIndex),
      confidence: activeConfidence,
    });
  }, [activeConfidence, activeResult, filteredResults, loading]);

  useEffect(() => {
    if (!activeOntologyUrl || !activeOntologySourceKey) return;

    const controller = new AbortController();

    apiClient
      .get<SenderRelationship[]>(activeOntologyUrl, {
        signal: controller.signal,
      })
      .then((response) => {
        if (controller.signal.aborted) return;
        setRelationshipState({
          sourceKey: activeOntologySourceKey,
          items: response,
          error: null,
        });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setRelationshipState({
          sourceKey: activeOntologySourceKey,
          items: [],
          error: "발신자 DAG를 불러오지 못했습니다.",
        });
      });

    return () => controller.abort();
  }, [activeOntologySourceKey, activeOntologyUrl]);

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedQuery = query.trim();
    searchSessionIdRef.current = createProductEventId(
      "context_search_session",
    );
    lastOpenedResultKeyRef.current = null;
    recordProductEvent("context_search_submitted", {
      surface: "context_search",
      search_session_id: searchSessionIdRef.current,
      query_length_bucket: bucketTextLength(trimmedQuery),
      filter_count: activeFilter === "all" ? 0 : 1,
      source_filters: activeFilter === "all" ? null : activeFilter,
    });
    setActiveFilter("all");
    setError(null);
    setResults([]);
    setActiveResultId(null);
    setLoading(Boolean(trimmedQuery));
    setSubmittedQuery(trimmedQuery);
  };

  const captureSenderRelationship = () => {
    const actionResult = activeResult;
    const actionSourceKey = activeOntologySourceKey;
    if (!actionResult?.source_message_id || !actionSourceKey) return;
    setCaptureState({ sourceKey: activeOntologySourceKey, status: "loading" });
    apiClient
      .post<SenderRelationship>("/api/ontology/relationships/capture-source", {
        source_message_id: actionResult.source_message_id,
      })
      .then((response) => {
        setRelationshipState({
          sourceKey: actionSourceKey,
          items: [response],
          error: null,
        });
        setCaptureState({
          sourceKey: actionSourceKey,
          status: "success",
        });
        recordProductEvent("context_search_result_action_created", {
          surface: "context_search",
          search_session_id: searchSessionIdRef.current,
          result_id: actionResult.id,
          action_id: `relationship:${response.source_message_id ?? actionResult.source_message_id}`,
          action_type: "relation_capture",
          source_backlink_present: Boolean(actionResult.source_message_id),
        });
      })
      .catch(() => {
        setCaptureState({
          sourceKey: actionSourceKey,
          status: "error",
        });
      });
  };

  // ⚡ Bolt: Wrap search results in useMemo to prevent O(N) re-renders when other state changes
  // 🎯 Why: Mapping over long lists of search results blocks the main thread during unrelated state updates.
  const resultList = useMemo(() => (
    <div className="divide-y divide-border">
      {loading ? (
        <div
          role="status"
          aria-live="polite"
          className="p-5 text-sm font-semibold text-muted-foreground"
        >
          맥락 검색 결과를 불러오는 중입니다.
        </div>
      ) : error ? (
        <div
          role="alert"
          className="m-4 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm font-semibold text-destructive"
        >
          <AlertCircle className="mr-2 inline size-4" aria-hidden="true" />
          {error}
        </div>
      ) : filteredResults.length === 0 ? (
        <div className="p-5 text-sm font-semibold text-muted-foreground">
          맥락 검색 결과가 없습니다.
        </div>
      ) : (
        filteredResults.map((result) => (
          <SearchResultItemComponent
            key={result.id}
            result={result}
            isActive={activeResult?.id === result.id}
            confidence={confidencePercent(result.score)}
            onSelect={setActiveResultId}
          />
        ))
      )}
    </div>
  ), [loading, error, filteredResults, activeResult?.id, setActiveResultId]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background text-foreground">
      <header className="shrink-0 border-b border-border bg-card px-4 py-4 md:px-8">
        <h1 className="sr-only">맥락 검색</h1>
        <form
          onSubmit={submitSearch}
          className="mx-auto flex w-full max-w-4xl gap-2"
        >
          <div className="relative min-w-0 flex-1">
            <label htmlFor="search-input" className="sr-only">맥락 검색</label>
            <Search
              className="absolute left-4 top-1/2 size-5 -translate-y-1/2 text-primary"
              aria-hidden="true"
            />
            <input
              id="search-input"
              ref={searchInputRef}
              type="search"
              inputMode="search"
              role="searchbox"
              aria-label="맥락 검색어 입력"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="메일, 일정, 파일, 사람, 의사결정 로그 맥락 검색..."
              className="h-12 w-full rounded-full border-2 border-primary/20 bg-background pl-12 pr-12 text-base shadow-sm transition-all focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/10 [&::-webkit-search-cancel-button]:hidden"
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  searchInputRef.current?.focus();
                }}
                className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                aria-label="맥락 검색어 지우기"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            )}
          </div>
          <button
            type="submit"
            disabled={loading}
            aria-busy={loading}
            className="h-12 shrink-0 rounded-lg bg-primary px-4 text-sm font-bold text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-wait disabled:opacity-60 inline-flex items-center justify-center"
          >
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            {loading ? "맥락 검색 중" : "맥락 검색"}
          </button>
        </form>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
        <aside className="max-h-[34dvh] w-full shrink-0 overflow-y-auto border-b border-border bg-card sm:max-h-[42dvh] md:max-h-none md:w-[400px] md:border-b-0 md:border-r">
          <div className="flex items-center justify-between border-b border-border p-5">
            <h2 className="font-bold">통합 맥락 검색 결과</h2>
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-bold text-primary">
              {results.length}건
            </span>
          </div>
          <div className="flex gap-2 overflow-x-auto border-b border-border p-4">
            {resultFilters.map((filter) => (
              <button
                key={filter.key}
                type="button"
                aria-pressed={activeFilter === filter.key}
                onClick={() => setActiveFilter(filter.key)}
                className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-1 focus-visible:ring-offset-background ${
                  activeFilter === filter.key
                    ? "bg-primary text-primary-foreground"
                    : "bg-secondary text-muted-foreground hover:bg-secondary/80"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
          {resultList}
        </aside>

        <main className="flex-1 overflow-y-auto bg-background p-4 pb-[calc(6rem+env(safe-area-inset-bottom))] md:p-8">
          <div className="mx-auto max-w-5xl space-y-6">
            {answerState.status === "done" && submittedQuery.trim() ? (
              <section
                aria-label="AI 답변"
                data-testid="grounded-answer-card"
                className="rounded-lg border border-primary/30 bg-primary/5 p-5 shadow-sm"
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-bold text-primary">AI 답변</h3>
                  {answerState.provenance ? (
                    <span className="text-xs text-muted-foreground">
                      {answerState.provenance}
                    </span>
                  ) : null}
                </div>
                <p className="whitespace-pre-wrap text-sm leading-6">
                  {answerState.answer}
                </p>
                {answerState.citations.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {answerState.citations.map((citation) => (
                      <button
                        key={citation.email_id}
                        type="button"
                        onClick={() => setActiveResultId(citation.email_id)}
                        className="rounded-full border border-primary/30 bg-card px-3 py-1 text-xs font-semibold text-primary hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                      >
                        근거: {citation.subject ?? `메일 #${citation.email_id}`}
                      </button>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}
            {!activeResult ? (
              <div className="rounded-lg border border-border bg-card p-6 text-sm font-semibold text-muted-foreground shadow-sm">
                결과를 선택하면 메일 스레드, 답장 추적, 발신자 관계를 함께
                보여줍니다.
              </div>
            ) : (
              <>
                <section
                  aria-label="맥락 검색 결과 상세"
                  className="rounded-lg border border-border bg-card p-5 shadow-sm md:p-6"
                >
                  <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                    <div className="flex min-w-0 items-start gap-4">
                      <div className="rounded-lg bg-primary/10 p-4">
                        <Mail
                          className="size-7 text-primary"
                          aria-hidden="true"
                        />
                      </div>
                      <div className="min-w-0">
                        <span className="mb-2 inline-block rounded bg-primary/10 px-2 py-0.5 text-xs font-bold text-primary">
                          메일 스레드
                        </span>
                        <h2 className="text-xl font-bold md:text-2xl">
                          {resultTitle(activeResult)}
                        </h2>
                        <p className="mt-1 text-sm text-muted-foreground">
                          {activeResult.sender}
                        </p>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center text-xs font-bold text-muted-foreground">
                      <div className="rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-foreground">
                          {activeResult.thread_id ? "연결됨" : "없음"}
                        </p>
                        <p className="mt-1">스레드 근거</p>
                      </div>
                      <div className="rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-foreground">
                          {activeResult.reply_count ?? 1}건
                        </p>
                        <p className="mt-1">답장 추적</p>
                      </div>
                      <div className="rounded-lg border border-border bg-background px-3 py-2">
                        <p className="text-foreground">
                          {activeConfidence === null ? "미제공" : `${activeConfidence}%`}
                        </p>
                        <p className="mt-1">신뢰도</p>
                      </div>
                    </div>
                  </div>
                  <div className="mb-5 flex flex-wrap gap-2">
                    <Link
                      href="/mail"
                      className="inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-3 text-xs font-bold text-foreground transition-colors hover:border-primary/30 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                    >
                      <Mail className="size-4" aria-hidden="true" />
                      메일 열기
                    </Link>
                    <Link
                      href="/calendar"
                      className="inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-3 text-xs font-bold text-foreground transition-colors hover:border-primary/30 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                    >
                      <CalendarDays className="size-4" aria-hidden="true" />
                      일정 후보 보기
                    </Link>
                    <button
                      type="button"
                      onClick={captureSenderRelationship}
                      disabled={!canCaptureRelationship || captureStatus === "loading"}
                      aria-busy={captureStatus === "loading"}
                      className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-xs font-bold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                    >
                      {captureStatus === "loading" ? (
                        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                      ) : (
                        <Network className="size-4" aria-hidden="true" />
                      )}
                      {captureStatus === "loading" ? "관계 캡처 중" : "관계 캡처"}
                    </button>
                  </div>

                  <div className="rounded-2xl border border-border bg-background/80 p-2">
                    <div
                      role="tablist"
                      aria-label="맥락 검색 결과 증거 상세"
                      className="grid gap-1 rounded-xl bg-secondary/50 p-1 sm:grid-cols-3"
                    >
                      {detailTabs.map((tab) => (
                        <button
                          key={tab.key}
                          type="button"
                          role="tab"
                          id={`search-detail-tab-${tab.key}`}
                          aria-controls={`search-detail-panel-${tab.key}`}
                          aria-selected={activeDetailTab === tab.key}
                          tabIndex={activeDetailTab === tab.key ? 0 : -1}
                          onClick={() => setActiveDetailTab(tab.key)}
                          className={`rounded-lg px-3 py-2 text-xs font-black transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                            activeDetailTab === tab.key
                              ? "bg-card text-primary shadow-sm"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>

                    <div
                      role="tabpanel"
                      id={`search-detail-panel-${activeDetailTab}`}
                      aria-labelledby={`search-detail-tab-${activeDetailTab}`}
                      className="p-4"
                    >
                      {activeDetailTab === "context" ? (
                        <div className="space-y-4">
                          <div className="rounded-xl border border-border bg-card p-4 text-sm leading-7 text-foreground">
                            {activeResult.snippet}
                          </div>
                          <p className="text-xs font-black text-primary">증거 바인딩</p>
                          <div className="flex flex-wrap gap-2 text-xs font-bold">
                            <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-blue-700">
                              <FileText className="size-3.5" aria-hidden="true" />
                              메일 원본
                            </span>
                            <span className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-indigo-700">
                              <CornerDownRight className="size-3.5" aria-hidden="true" />
                              {activeResult.thread_id ? "스레드 근거 연결" : "단일 메일"}
                            </span>
                            <span className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 ${confidenceTone(activeConfidence)}`}>
                              <CheckCircle2 className="size-3.5" aria-hidden="true" />
                              {confidenceLabel(activeConfidence)}
                            </span>
                          </div>
                        </div>
                      ) : null}

                      {activeDetailTab === "source" ? (
                        <div className="grid gap-3 text-sm md:grid-cols-2">
                          <div className="rounded-xl border border-border bg-card p-4">
                            <p className="text-xs font-black text-primary">증거 바인딩</p>
                            <p className="mt-2 font-semibold text-foreground">
                              {activeResult.source_message_id ? "원본 메시지 필터로 관계 API를 조회합니다." : "원본 메시지 필터가 없는 결과입니다."}
                            </p>
                            <p className="mt-2 text-xs leading-5 text-muted-foreground">
                              관계 조회는 선택된 맥락 검색 결과의 source/thread 범위 안에서만 수행됩니다.
                            </p>
                          </div>
                          <div className="rounded-xl border border-border bg-card p-4">
                            <p className="text-xs font-black text-primary">관계 상태</p>
                            <p className="mt-2 font-semibold text-foreground">
                              {relationshipsLoading
                                ? "관계 원본 확인 중"
                                : relationshipError
                                  ? "관계 원본 오류"
                                  : relationships.length > 0
                                    ? `${relationships.length}개 관계 연결`
                                    : "관계 원본 없음"}
                            </p>
                            <p className="mt-2 text-xs leading-5 text-muted-foreground">
                              관계가 없으면 원본 메시지 기준 캡처를 실행해 판단 근거를 생성합니다.
                            </p>
                          </div>
                        </div>
                      ) : null}

                      {activeDetailTab === "assist" ? (
                        <div className="rounded-xl border border-purple-200 bg-purple-50/70 p-4">
                          <div className="flex items-start gap-3">
                            <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-purple-600 text-white">
                              <Sparkles className="size-4" aria-hidden="true" />
                            </div>
                            <div>
                              <p className="text-sm font-black text-purple-900">판단 보조</p>
                              <p className="mt-2 text-sm leading-6 text-purple-900/80">
                                이 화면의 AI/관계 정보는 검색 점수, 원본 메시지, 스레드 범위를 함께 보여주는 보조 근거입니다. 외부 실행은 사용자가 메일, 일정, 관계 캡처 액션을 명시적으로 선택할 때만 진행됩니다.
                              </p>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </section>

                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-lg font-bold">관계 맥락과 타임라인</h2>
                  <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
                    source/thread API 연결
                  </span>
                </div>

                <div className="grid gap-6 xl:grid-cols-2">
                  <section className="flex min-h-[420px] flex-col rounded-lg border border-border bg-card p-5 shadow-sm md:p-6">
                    <div className="mb-4 flex items-center gap-2">
                      <Network
                        className="size-5 text-primary"
                        aria-hidden="true"
                      />
                      <h3 className="text-lg font-bold">
                        발신자 DAG (Ontology)
                      </h3>
                    </div>
                    <SenderDagPanel
                      relationships={relationships}
                      loading={relationshipsLoading}
                      error={relationshipError}
                      canCapture={canCaptureRelationship}
                      captureStatus={captureStatus}
                      onCapture={captureSenderRelationship}
                    />
                    <div className="my-4 border-t border-border" />
                    <h4 className="mb-3 text-sm font-black text-foreground">
                      관계 맥락
                    </h4>
                    <div className="relative min-h-[320px] flex-1 overflow-hidden rounded-lg border border-border bg-background shadow-inner">
                      <NetworkGraph />
                    </div>
                  </section>

                  <section className="rounded-lg border border-border bg-card p-5 shadow-sm md:p-6">
                    <div className="mb-6 flex items-center gap-2">
                      <Clock
                        className="size-5 text-primary"
                        aria-hidden="true"
                      />
                      <h3 className="text-lg font-bold">타임라인 (Timeline)</h3>
                    </div>
                    <div className="relative ml-3 space-y-6 border-l-2 border-border">
                      <div className="relative pl-6">
                        <div className="absolute -left-[9px] top-1 size-4 rounded-full border-2 border-card bg-primary" />
                        <p className="mb-1 text-xs font-bold text-primary">
                          현재
                        </p>
                        <h4 className="inline-block rounded bg-secondary px-2 py-1 text-sm font-bold">
                          맥락 검색 결과 선택됨
                        </h4>
                      </div>
                      <div className="relative pl-6">
                        <div className="absolute -left-[9px] top-1 size-4 rounded-full border-2 border-card bg-border" />
                        <p className="mb-1 text-xs font-bold text-muted-foreground">
                          {formatResultDate(activeResult.date)}
                        </p>
                        <h4 className="text-sm font-bold text-muted-foreground">
                          {resultTitle(activeResult)}
                        </h4>
                        <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                          <CheckCircle2 className="size-3" aria-hidden="true" />
                          thread reply_count={activeResult.reply_count ?? 1}
                        </p>
                      </div>
                      {activeResult.thread_id ? (
                        <div className="relative pl-6">
                          <div className="absolute -left-[9px] top-1 size-4 rounded-full border-2 border-card bg-border" />
                          <p className="mb-1 text-xs font-bold text-muted-foreground">
                            스레드 기준
                          </p>
                          <h4 className="flex items-center gap-2 text-sm font-bold text-muted-foreground">
                            <CornerDownRight
                              className="size-4"
                              aria-hidden="true"
                            />
                            {activeResult.thread_id}
                          </h4>
                        </div>
                      ) : null}
                    </div>
                  </section>
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
