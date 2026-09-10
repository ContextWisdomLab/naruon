import React, { useCallback, useEffect, useRef, useState, memo } from 'react';
import { apiClient } from '@/lib/api-client';
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2, Mail, MessagesSquare, Network, Search, Sparkles, X } from "lucide-react";
import { formatEmailDate } from "@/lib/email-threading";
import { toMailDisplayText } from "@/lib/mail-text";

interface EmailItem {
  id: number;
  subject: string | null;
  sender: string;
  date?: string;
  snippet: string;
  unread?: boolean;
  is_read?: boolean; // IMAP \Seen read state from the API
  thread_id?: string; // O3: email threading support
  reply_count?: number;
  has_draft?: boolean;
  is_self_sent?: boolean;
  requires_reply?: boolean;
  schedule_conflict?: boolean;
}

export type MailFolder = 'inbox' | 'sent';

const folderRequests = new Map<MailFolder, Promise<EmailItem[]>>();

function folderEndpoint(folder: MailFolder) {
  return folder === 'sent' ? '/api/emails?folder=sent' : '/api/emails';
}

async function fetchFolderEmails(folder: MailFolder) {
  if (folderRequests.has(folder)) return folderRequests.get(folder)!;

  const request = apiClient.get<{ emails: EmailItem[] }>(folderEndpoint(folder))
    .then((data) => data.emails || [])
    .finally(() => {
      folderRequests.delete(folder);
    });
  folderRequests.set(folder, request);
  return request;
}



// ⚡ Bolt: Extracted and memoized individual email items
// 🎯 Why: Previously, selecting a single email caused the entire list of 50+ items to re-render.
// 💡 Impact: Reduces re-renders to only 2 items per selection change (the old active item and the new one), saving CPU cycles.
const EmailListItemComponent = memo(function EmailListItemComponent({

  email,
  selected,
  onSelectEmail
}: {
  email: EmailItem;
  selected: boolean;
  onSelectEmail: (id: number) => void;
}) {
  const safeSender = toMailDisplayText(email.sender, '보낸 사람');
  const subject = email.subject?.trim() === '' ? undefined : email.subject;
  const safeSubject = toMailDisplayText(subject, '(제목 없음)');
  const safeSnippet = toMailDisplayText(email.snippet);

  return (
    <button type="button"
      onClick={() => onSelectEmail(email.id)}
      aria-current={selected ? "true" : undefined}
      className={`group relative flex min-h-20 flex-col items-start gap-2 overflow-hidden rounded-2xl border p-3 pl-4 text-left text-sm transition-all hover:border-primary/35 hover:bg-primary/5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${selected ? 'border-primary/60 bg-primary/10 shadow-[0_16px_36px_rgba(37,99,255,0.14)]' : 'border-border bg-card'}`}
    >
      <span className={`absolute inset-y-3 left-0 w-1 rounded-r-full ${selected ? 'bg-primary' : 'bg-transparent group-hover:bg-primary/50'}`} aria-hidden="true" />
      <div className="flex w-full flex-col gap-1">
        <div className="flex items-center">
          <div className="flex items-center gap-2">
            <Avatar className="h-8 w-8 border border-primary/10 bg-primary/10 text-primary">
              <AvatarFallback>{safeSender ? safeSender.charAt(0).toUpperCase() : 'U'}</AvatarFallback>
            </Avatar>
            <div className="max-w-[140px] truncate font-bold text-foreground">{safeSender}</div>
          </div>
          <div className="ml-auto max-w-24 truncate text-right text-xs text-muted-foreground">
            {formatEmailDate(email.date)}
          </div>
        </div>
        <div className="flex items-center gap-2 w-full">
          <div className="truncate text-sm font-bold flex-1 text-foreground">{safeSubject}</div>
          {email.reply_count && email.reply_count > 1 && (
            <Badge variant="secondary" className="h-5 whitespace-nowrap border border-primary/10 bg-primary/10 px-2 py-0 text-[10px] leading-none text-primary flex items-center gap-1">
              <MessagesSquare className="w-3 h-3" />
              {email.reply_count}개 메시지
            </Badge>
          )}
        </div>
      </div>
      <div className="line-clamp-2 w-full text-xs leading-5 text-muted-foreground">
        {safeSnippet}
      </div>
      {(email.unread || email.is_read === false || email.has_draft || email.is_self_sent || email.requires_reply || email.schedule_conflict) && (
        <div className="flex items-center gap-2 flex-wrap">
          {(email.unread || email.is_read === false) && <Badge variant="default" className="bg-emerald-500 text-[10px] text-white">안 읽음</Badge>}
          {email.has_draft && <Badge variant="secondary" className="border-blue-500/20 bg-blue-500/10 text-[10px] text-blue-700">답장 초안</Badge>}
          {email.is_self_sent && <Badge variant="secondary" className="border-purple-500/20 bg-purple-500/10 text-[10px] text-purple-700">지식 정리</Badge>}
          {email.requires_reply && <Badge variant="outline" className="border-primary/30 text-[10px] text-primary bg-primary/5">응답 대기 중</Badge>}
          {email.schedule_conflict && <Badge variant="outline" className="border-emerald-500/30 text-[10px] text-emerald-700 bg-emerald-500/5">일정 충돌 조율</Badge>}
        </div>
      )}
    </button>
  );
});

export function EmailList({
  onSelectEmail,
  selectedEmailId,
  folder = 'inbox',
}: {
  onSelectEmail: (id: number) => void;
  selectedEmailId?: number | null;
  folder?: MailFolder;
}) {
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [emptyStateMode, setEmptyStateMode] = useState<'folder' | 'search'>('folder');
  const searchInputRef = useRef<HTMLInputElement>(null);
  const requestSequenceRef = useRef(0);

  const fetchEmails = useCallback(async (query = "") => {
    const normalizedQuery = query.trim();
    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    setEmptyStateMode(normalizedQuery === "" ? 'folder' : 'search');
    setLoading(true);
    setError(null);
    setIsSearching(normalizedQuery !== "");
    try {
      const nextEmails = normalizedQuery === ""
        ? await fetchFolderEmails(folder)
        : (await apiClient.post<{ results: EmailItem[] }>('/api/search', { query })).results || [];
      if (requestSequence !== requestSequenceRef.current) return;
      setEmails(nextEmails);
    } catch (err: unknown) {
      if (requestSequence !== requestSequenceRef.current) return;
      setError(err instanceof Error ? err.message : "Failed to load emails");
    } finally {
      if (requestSequence === requestSequenceRef.current) {
        setLoading(false);
        setIsSearching(false);
      }
    }
  }, [folder]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Initial inbox fetch synchronizes client state with the backend.
    fetchEmails();
  }, [fetchEmails]);

  const folderCopy = folder === 'sent'
    ? {
        title: '보낸 메일',
        description: '답변 대기, 회신 완료, 나에게 보낸 지식 정리 후보를 추적합니다.',
        primaryBadge: '답변 추적',
        secondaryBadge: '지식 정리',
        focusLabel: '보낸 메일 추적',
        focusText: '응답 대기 스레드와 self-sent 지식 후보를 표시합니다',
      }
    : {
        title: '받은편지함',
        description: '중요 메일을 맥락과 실행 흐름으로 정리합니다.',
        primaryBadge: '맥락 종합',
        secondaryBadge: '실행 항목',
        focusLabel: '오늘의 판단 포인트',
        focusText: '메일 데이터 기반으로 판단 포인트를 표시합니다',
      };
  const emptyCopy = emptyStateMode === 'search'
    ? {
        title: '맥락 검색 결과가 없습니다',
        body: '맥락 검색어를 바꾸거나 메일 동기화 상태를 확인하세요.',
      }
    : folder === 'sent'
      ? {
          title: '보낸 메일이 없습니다',
          body: 'SMTP/IMAP 동기화 후 보낸 스레드와 답변 대기 상태가 표시됩니다.',
        }
      : {
          title: '받은 메일이 없습니다',
          body: '메일 동기화 후 받은 스레드가 표시됩니다.',
        };
  const searchBusy = isSearching || loading;

  return (
    <div className="flex h-full min-h-0 w-full flex-col border-r border-border/80 bg-card/95">
      <div className="border-b border-border/80 bg-gradient-to-br from-card via-card to-primary/5 p-4">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary">
              <Sparkles className="size-3.5" aria-hidden="true" />
              Naruon Mail
            </div>
            <h2 className="mt-1 text-2xl font-black tracking-tight text-foreground">{folderCopy.title}</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{folderCopy.description}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-bold">
              <span className="inline-flex items-center gap-1 rounded-full border border-primary/15 bg-primary/10 px-2.5 py-1 text-primary">
                <Network className="size-3" aria-hidden="true" />
                {folderCopy.primaryBadge}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/15 bg-emerald-500/10 px-2.5 py-1 text-emerald-700">
                <CheckCircle2 className="size-3" aria-hidden="true" />
                {folderCopy.secondaryBadge}
              </span>
            </div>
            <div className="mt-3 rounded-2xl border border-primary/15 bg-background/80 px-3 py-2 text-xs leading-5 shadow-inner shadow-slate-950/[0.02]">
              <span className="font-bold text-primary">{folderCopy.focusLabel}</span>
              <span className="mx-2 text-muted-foreground">·</span>
              <span className="font-semibold text-foreground">{folderCopy.focusText}</span>
            </div>
          </div>
          <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-[0_12px_28px_rgba(37,99,255,0.28)]">
            <Mail className="size-5" aria-hidden="true" />
          </span>
        </div>
        <form
          onSubmit={(e: React.FormEvent) => {
            e.preventDefault();
            fetchEmails(searchQuery);
          }}
          className="flex gap-2"
        >
          <label htmlFor="email-search" className="sr-only">메일 맥락 검색</label>
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              id="email-search"
              ref={searchInputRef}
              aria-label="메일 맥락 검색"
              placeholder="메일, 사람, 키워드 맥락 검색..."
              value={searchQuery}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
              type="search"
              inputMode="search"
              role="searchbox"
              className="h-10 rounded-xl border-input bg-background/80 pl-9 pr-9 shadow-inner shadow-slate-950/[0.02] [&::-webkit-search-cancel-button]:hidden"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery("");
                  void fetchEmails("");
                  searchInputRef.current?.focus();
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-full"
                aria-label="맥락 검색어 지우기"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            )}
          </div>
          <Button type="submit" disabled={searchBusy} aria-busy={searchBusy} className="h-10 rounded-xl px-4">
            {searchBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            {searchBusy ? "맥락 검색 중" : "맥락 검색"}
          </Button>
        </form>
      </div>
      <ScrollArea className="min-h-0 flex-1 w-full">
        <div className="flex flex-col gap-2 p-3 pb-[calc(7rem+env(safe-area-inset-bottom))] lg:pb-3">
          {loading ? (
            <div role="status" aria-live="polite" className="rounded-2xl border border-border bg-background/70 p-4 text-sm text-muted-foreground">메일을 불러오는 중입니다...</div>
          ) : error ? (
            <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-600">{error}</div>
          ) : emails.length === 0 ? (
            <div role="status" aria-live="polite" className="rounded-2xl border border-dashed border-border bg-background/70 p-5 text-sm text-muted-foreground">
              <p className="font-bold text-foreground">{emptyCopy.title}</p>
              <p className="mt-1 text-xs leading-5">{emptyCopy.body}</p>
            </div>
          ) : (
            emails.map((email: EmailItem) => (
              <EmailListItemComponent
                key={email.id}
                email={email}
                selected={selectedEmailId === email.id}
                onSelectEmail={onSelectEmail}
              />
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
