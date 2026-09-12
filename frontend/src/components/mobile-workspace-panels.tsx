"use client";

import { useEffect, useState } from 'react';

import { apiClient } from '@/lib/api-client';
import { isMailListItem } from '@/lib/mail-response';
import { toSafeReactText } from '@/lib/safe-text';

type MobileSearchResult = {
  id: number;
  subject: string | null;
  sender: string;
  date: string;
  snippet: string;
  reply_count?: number;
};

type MobileSearchResponse = {
  results: MobileSearchResult[];
};

type MobilePanelCopy = {
  eyebrow: string;
  title: string;
  description: string;
  loading: string;
  empty: string;
  error: string;
  query: string;
  limit: number;
};

const mobileSearchCopy: MobilePanelCopy = {
  eyebrow: '맥락 검색',
  title: '메일, 첨부, 일정, 사람을 한 번에 검색합니다.',
  description: '흩어진 대화와 파일을 하나의 판단 흐름으로 묶어 보여주는 모바일 맥락 검색 진입점입니다.',
  loading: '맥락 검색 결과를 불러오는 중입니다.',
  empty: '맥락 검색 결과가 없습니다.',
  error: '맥락 검색을 불러오지 못했습니다.',
  query: '메일 첨부 일정 사람',
  limit: 4,
};

const mobileCalendarCopy: MobilePanelCopy = {
  eyebrow: '일정 연결',
  title: '일정 반영 대기',
  description: '메일에서 추출한 회의, 마감, 후속 조치를 모바일에서 바로 확인합니다.',
  loading: '일정 후보를 불러오는 중입니다.',
  empty: '일정 후보가 없습니다.',
  error: '일정 후보를 불러오지 못했습니다.',
  query: '회의 마감 후속 조치 일정',
  limit: 3,
};

function formatResultDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '날짜 미정';
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(date);
}

function MobileApiPanel({ copy }: { copy: MobilePanelCopy }) {
  const [status, setStatus] = useState<'loading' | 'success' | 'empty' | 'error'>('loading');
  const [results, setResults] = useState<MobileSearchResult[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    void apiClient.post<MobileSearchResponse>('/api/search', { query: copy.query, limit: copy.limit }, { signal: controller.signal })
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
  }, [copy.limit, copy.query]);

  return (
    <>
      <div className="rounded-2xl border border-primary/15 bg-card p-4 shadow-sm">
        <p className="text-xs font-bold text-primary">{copy.eyebrow}</p>
        <h2 className="mt-2 text-lg font-black text-foreground">{copy.title}</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.description}</p>
      </div>
      <div className="mt-4 space-y-3">
        {status === 'loading' ? (
          <div role="status" aria-live="polite" className="rounded-2xl border border-border bg-card px-4 py-3 text-sm font-semibold text-muted-foreground shadow-sm">
            {copy.loading}
          </div>
        ) : null}
        {status === 'error' ? (
          <div role="alert" className="rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive shadow-sm">
            {copy.error}
          </div>
        ) : null}
        {status === 'empty' ? (
          <div className="rounded-2xl border border-border bg-card px-4 py-3 text-sm font-semibold text-muted-foreground shadow-sm">
            {copy.empty}
          </div>
        ) : null}
        {status === 'success' ? results.map((result) => {
          const safeSubject = toSafeReactText(result.subject?.trim() || null, '(제목 없음)');
          const safeSender = toSafeReactText(result.sender);
          const safeSnippet = toSafeReactText(result.snippet);

          return (
            <article key={result.id} className="rounded-2xl border border-border bg-card p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-bold text-foreground">{safeSubject}</p>
                <span className="shrink-0 text-xs font-semibold text-muted-foreground">{formatResultDate(result.date)}</span>
              </div>
              <p className="mt-1 text-xs font-semibold text-primary">{safeSender}</p>
              <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">{safeSnippet}</p>
            </article>
          );
        }) : null}
      </div>
    </>
  );
}

export function MobileSearchPanel() {
  return <MobileApiPanel copy={mobileSearchCopy} />;
}

export function MobileCalendarPanel() {
  return <MobileApiPanel copy={mobileCalendarCopy} />;
}
