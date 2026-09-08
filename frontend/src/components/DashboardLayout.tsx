'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  Bell,
  Briefcase,
  CalendarDays,
  CheckCircle2,
  Database,
  FileText,
  HelpCircle,
  Home,
  Inbox,
  Menu,
  PenLine,
  Search,
  Send,
  Sparkles,
  Star,
  MoreHorizontal,
  Settings,
  ShieldCheck,
  UserCircle,
  X
} from 'lucide-react';

import { setMobileWorkspaceView, useMobileWorkspaceView } from '@/lib/mobile-workspace';
import { setWorkspaceStartupView, useWorkspaceStartupView, type WorkspaceStartupView } from '@/lib/workspace-preferences';

const mailNavItems = [
  { label: '받은 메일', description: '우선순위 인박스', icon: Inbox, href: '/mail?folder=inbox' },
  { label: '중요 메일', description: '중요 표시된 메일', icon: Star, href: '/mail?folder=starred' },
  { label: '보낸 메일', description: '답변 추적 대상', icon: Send, href: '/mail?folder=sent' },
  { label: '임시 보관함', description: '작성 중인 메일', icon: FileText, href: '/mail?folder=drafts' },
  { label: '전체 메일', description: '중복 정리 대상', icon: Home, href: '/mail?folder=all' },
];

const mobileWorkspaceItems = [
  { label: '받은편지함', icon: Inbox, view: 'inbox' as const },
  { label: '맥락 검색', icon: Search, view: 'search' as const },
  { label: '일정', icon: CalendarDays, view: 'calendar' as const },
  { label: '더보기', icon: MoreHorizontal, view: 'actions' as const },
];

const primaryNavItems = [
  { label: '홈', href: '/', icon: Home },
  { label: '메일', href: '/mail', icon: Inbox },
  { label: '일정', href: '/calendar', icon: CalendarDays },
  { label: '작업', href: '/tasks', icon: CheckCircle2 },
  { label: '프로젝트', href: '/projects', icon: Briefcase },
  { label: '맥락 검색', href: '/search', icon: Search },
  { label: 'AI 허브', href: '/ai-hub', icon: Sparkles },
  { label: '데이터', href: '/data', icon: Database },
  { label: '보안', href: '/security', icon: ShieldCheck },
  { label: '설정', href: '/settings', icon: Settings },
];

const startupViewItems = [
  { label: '홈', view: 'dashboard' as const, description: '오늘의 실행 맥락 종합' },
  { label: '메일', view: 'email' as const, description: '받은편지함 작업공간' },
  { label: '일정', view: 'calendar' as const, description: '캘린더 연결 먼저 보기' },
];

const mobileWorkspaceMenuItems = [
  { label: '받은편지함', description: '메일 스레드', icon: Inbox, href: '#mobile-inbox', view: 'inbox' as const },
  { label: '맥락 검색', description: '메일, 첨부, 일정, 사람 맥락 검색', icon: Search, href: '#mobile-search', view: 'search' as const },
  { label: '일정 연결', description: '일정 반영 후보', icon: CalendarDays, href: '#mobile-calendar', view: 'calendar' as const },
  { label: '판단 보조 실행', description: '관계 맥락과 실행 항목', icon: Sparkles, href: '#mobile-actions', view: 'actions' as const },
];

const headerActions = [
  { label: '일정 반영', action: 'calendar-sync', message: '메일 상세 패널에서 실행 항목을 캘린더에 반영합니다.', icon: CalendarDays },
  { label: '답장 초안', action: 'reply-draft', message: '메일 상세 패널에서 답장 초안을 생성합니다.', icon: PenLine },
  { label: '실행 항목 생성', action: 'create-task', message: '메일 상세 패널에서 메일 후속 작업을 실행 항목으로 정리합니다.', icon: CheckCircle2 },
];




const locationChangeEvent = 'naruon:location-change';
let historyListenerInstalled = false;

function emitLocationChange() {
  window.dispatchEvent(new Event(locationChangeEvent));
}

function installHistoryListener() {
  if (typeof window === 'undefined' || historyListenerInstalled) return;
  const pushState = window.history.pushState;
  const replaceState = window.history.replaceState;

  window.history.pushState = function patchedPushState(this: History, ...args: Parameters<History['pushState']>) {
    pushState.apply(this, args);
    emitLocationChange();
  } as History['pushState'];

  window.history.replaceState = function patchedReplaceState(this: History, ...args: Parameters<History['replaceState']>) {
    replaceState.apply(this, args);
    emitLocationChange();
  } as History['replaceState'];

  historyListenerInstalled = true;
}

function subscribeToLocationChanges(callback: () => void) {
  if (typeof window === 'undefined') return () => {};
  installHistoryListener();
  window.addEventListener(locationChangeEvent, callback);
  window.addEventListener('popstate', callback);
  return () => {
    window.removeEventListener(locationChangeEvent, callback);
    window.removeEventListener('popstate', callback);
  };
}

function getCurrentSearch() {
  return typeof window === 'undefined' ? '' : window.location.search;
}

function getServerSearch() {
  return '';
}

function useCurrentSearchParams() {
  const search = useSyncExternalStore(subscribeToLocationChanges, getCurrentSearch, getServerSearch);
  return new URLSearchParams(search);
}

function splitHref(href: string) {
  const [pathWithQuery, hash = ''] = href.split('#');
  const [path = '/', query = ''] = pathWithQuery.split('?');
  return { path: path || '/', query, hash: hash ? `#${hash}` : '' };
}

type SearchParamsLike = Pick<URLSearchParams, 'get'>;

function isActivePath(
  pathname: string | null,
  href: string,
  currentHash = '',
  currentSearchParams?: SearchParamsLike | null,
) {
  if (!pathname) return false;
  const { path, query, hash } = splitHref(href);
  if (hash) {
    return pathname === path && currentHash === hash;
  }
  const pathMatch = path === '/'
    ? pathname === '/'
    : pathname === path || pathname.startsWith(`${path}/`);
  if (!pathMatch) return false;
  if (!query) return true;
  if (!currentSearchParams) return false;
  const targetSearchParams = new URLSearchParams(query);
  for (const [key, value] of targetSearchParams.entries()) {
    if (currentSearchParams.get(key) !== value) return false;
  }
  return true;
}

export function NavLink({
  label,
  description,
  icon: Icon,
  href = '#main-content',
}: {
  label: string;
  description?: string;
  href?: string;
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
}) {
  const pathname = usePathname();
  const searchParams = useCurrentSearchParams();
  const [currentHash, setCurrentHash] = useState('');

  useEffect(() => {
    const updateHash = () => setCurrentHash(window.location.hash);
    updateHash();
    const nextTick = window.setTimeout(updateHash, 0);
    window.addEventListener('hashchange', updateHash);
    window.addEventListener('popstate', updateHash);
    return () => {
      window.clearTimeout(nextTick);
      window.removeEventListener('hashchange', updateHash);
      window.removeEventListener('popstate', updateHash);
    };
  }, [pathname]);

  const active = isActivePath(pathname, href, currentHash, searchParams);

  return (
    <Link
      href={href}
      aria-current={active ? (splitHref(href).hash ? 'location' : 'page') : undefined}
      className={`group flex min-h-9 items-center gap-3 rounded-xl px-3 py-2 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
        active
          ? 'bg-primary text-primary-foreground shadow-[0_12px_28px_rgba(37,99,255,0.24)]'
          : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-primary'
      }`}
    >
      <Icon className="size-4" aria-hidden={true} />
      <span className="flex flex-col leading-tight">
        <span className="font-semibold">{label}</span>
        <span className={`text-[11px] ${active ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>
          {description}
        </span>
      </span>
    </Link>
  );
}

function PrimaryNavLink({
  label,
  href,
  icon: Icon,
}: {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
}) {
  const pathname = usePathname();
  const searchParams = useCurrentSearchParams();
  const isActiveDestination = isActivePath(pathname, href, '', searchParams);
  const linkRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    if (!isActiveDestination) return;
    let animationFrame = 0;
    const scheduleVisibilityCorrection = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(() => {
        animationFrame = 0;
        const activeLink = linkRef.current;
        const primaryNavigation = activeLink?.closest('nav');
        if (!activeLink || !primaryNavigation) return;
        const navigationRect = primaryNavigation.getBoundingClientRect();
        const activeLinkRect = activeLink.getBoundingClientRect();
        const navigationInset = 16;
        if (activeLinkRect.left < navigationRect.left + navigationInset) {
          primaryNavigation.scrollLeft -= navigationRect.left + navigationInset - activeLinkRect.left;
        } else if (activeLinkRect.right > navigationRect.right - navigationInset) {
          primaryNavigation.scrollLeft += activeLinkRect.right - (navigationRect.right - navigationInset);
        }
      });
    };
    scheduleVisibilityCorrection();
    window.addEventListener('resize', scheduleVisibilityCorrection);
    return () => {
      window.removeEventListener('resize', scheduleVisibilityCorrection);
      window.cancelAnimationFrame(animationFrame);
    };
  }, [isActiveDestination]);

  return (
    <Link
      ref={linkRef}
      href={href}
      aria-current={isActiveDestination ? 'page' : undefined}
      className={`inline-flex h-10 shrink-0 whitespace-nowrap items-center gap-2 rounded-xl px-3 text-xs font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
        isActiveDestination ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-primary/10 hover:text-primary'
      }`}
    >
      <Icon className="size-4" aria-hidden={true} />
      {label}
    </Link>
  );
}

function HeaderActionButton({
  label,
  action,
  icon: Icon,
}: {
  label: string;
  action: string;
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
}) {
  function handleClick() {
    window.dispatchEvent(new CustomEvent('naruon:header-action', { detail: { action } }));
  }

  return (
    <button
      type="button"
      data-header-action={action}
      popoverTarget={`header-action-${action}`}
      onClick={handleClick}
      className="inline-flex h-10 items-center gap-2 rounded-xl border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm transition-colors hover:border-primary/30 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
    >
      <Icon className="size-4 text-primary" aria-hidden={true} />
      {label}
    </button>
  );
}

export function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const searchParams = useCurrentSearchParams();
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');
  const globalSearchInputRef = useRef<HTMLInputElement>(null);
  const activeMobileView = useMobileWorkspaceView();
  const startupView = useWorkspaceStartupView();

  useEffect(() => {
    if (!isWorkspaceMenuOpen || typeof document === 'undefined') return undefined;
    const previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousBodyOverflow;
    };
  }, [isWorkspaceMenuOpen]);

  function closeMobileWorkspaceMenu() {
    const menu = document.getElementById('mobile-workspace-menu') as (HTMLElement & { hidePopover?: () => void }) | null;
    menu?.hidePopover?.();
    setIsWorkspaceMenuOpen(false);
  }

  function handleMobileWorkspaceChange(
    view: (typeof mobileWorkspaceItems)[number]['view'],
    event?: React.MouseEvent<HTMLAnchorElement>,
  ) {
    event?.preventDefault();
    closeMobileWorkspaceMenu();
    setMobileWorkspaceView(view);
  }

  function handleHeaderAction(action: string) {
    window.dispatchEvent(new CustomEvent('naruon:header-action', { detail: { action } }));
  }

  function handleStartupViewChange(view: WorkspaceStartupView) {
    setWorkspaceStartupView(view);
    closeMobileWorkspaceMenu();
    if (window.location.hash.startsWith('#mobile-')) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
    }
    if (view === 'dashboard') {
      setMobileWorkspaceView('inbox', { updateHash: false });
    }
    if (view === 'email') {
      setMobileWorkspaceView('inbox', { updateHash: false });
    }
    if (view === 'calendar') {
      setMobileWorkspaceView('calendar', { updateHash: false });
    }
  }

  return (
    <div className="relative flex h-screen overflow-hidden bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:right-4 focus:top-4 focus:z-50 focus:rounded-xl focus:bg-card focus:px-4 focus:py-2 focus:text-center focus:text-sm focus:font-semibold focus:text-primary focus:shadow-lg focus:outline-none focus:ring-3 focus:ring-ring/40"
      >
        본문 바로가기
      </a>

      {/* Sidebar removed to match branding assets */}

      <main id="main-content" className="flex min-w-0 flex-1 flex-col overflow-hidden pb-16 lg:pb-0">
        <header aria-label="Naruon workspace header" className="flex min-h-16 items-center gap-3 border-b border-border/70 bg-card/85 px-4 backdrop-blur-xl lg:px-6">
          <button
            type="button"
            aria-label="워크스페이스 메뉴 열기"
            aria-controls="mobile-workspace-menu"
            aria-expanded={isWorkspaceMenuOpen}
            aria-haspopup="dialog"
            popoverTarget="mobile-workspace-menu"
            onClick={() => setIsWorkspaceMenuOpen((open) => !open)}
            className="grid size-10 place-items-center rounded-xl border border-border text-muted-foreground transition-colors hover:border-primary/30 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 xl:hidden"
          >
            <Menu className="size-5" aria-hidden="true" />
          </button>
          <div className="flex shrink-0 items-center gap-2">
            <Image src="/brand/naruon-symbol.svg" alt="Naruon" width={32} height={32} style={{ width: '32px', height: '32px' }} />
            <span className="text-lg font-black tracking-tight">Naruon</span>
          </div>
          <nav aria-label="Primary workspace navigation" className="hidden max-w-[44vw] scroll-px-3 items-center gap-1 overflow-x-auto xl:flex 2xl:max-w-none">
            {primaryNavItems.map((item) => (
              <PrimaryNavLink key={item.href} {...item} />
            ))}
          </nav>
          <div className="relative hidden min-w-0 flex-1 items-center rounded-2xl border border-border bg-background/80 px-4 py-2 text-sm text-muted-foreground shadow-inner shadow-slate-950/[0.02] xl:flex">
            <label htmlFor="global-search-input" className="sr-only">맥락 검색</label>
            <Search className="mr-2 size-4 text-primary" aria-hidden="true" />
            <input
              id="global-search-input"
              ref={globalSearchInputRef}
              className="min-w-0 flex-1 bg-transparent pr-8 outline-none placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:hidden"
              inputMode="search"
              role="searchbox"
              value={globalSearchQuery}
              onChange={(event) => setGlobalSearchQuery(event.target.value)}
              placeholder="맥락, 사람, 파일, 판단 포인트 맥락 검색..."
              type="search"
            />
            {globalSearchQuery ? (
              <button
                type="button"
                aria-label="맥락 검색어 지우기"
                onClick={() => {
                  setGlobalSearchQuery('');
                  globalSearchInputRef.current?.focus();
                }}
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            ) : null}
          </div>
          <section aria-label="Desktop startup preference" className="hidden shrink-0 items-center gap-1 rounded-2xl border border-border bg-background/80 p-1 shadow-sm lg:flex">
            <span className="px-2 text-[11px] font-black text-muted-foreground">시작 화면</span>
            {startupViewItems.map(({ label, view, description }) => {
              const active = startupView === view;
              return (
                <button
                  key={view}
                  type="button"
                  data-desktop-startup-view={view}
                  aria-pressed={active}
                  title={description}
                  onClick={() => handleStartupViewChange(view)}
                  className={`h-8 rounded-xl px-2 text-[11px] font-black transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                    active ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-primary/10 hover:text-primary'
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </section>
          <div data-testid="header-action-group" className="ml-auto hidden shrink-0 flex-wrap items-center justify-end gap-2 lg:flex">
            {headerActions.map(({ label, action, icon: Icon }) => (
              <HeaderActionButton key={action} label={label} action={action} icon={Icon} />
            ))}
            {headerActions.map(({ action, message }) => (
              <div
                key={`${action}-popover`}
                id={`header-action-${action}`}
                popover="auto"
                className="max-w-xs rounded-2xl border border-border bg-card p-4 text-sm font-semibold text-foreground shadow-[0_18px_50px_rgba(15,23,42,0.18)] backdrop:bg-transparent"
              >
                {message}
              </div>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2 xl:ml-0">
            <Link href="/security" aria-label="알림 보기" className="hidden size-10 place-items-center rounded-xl border border-border text-muted-foreground transition-colors hover:border-primary/30 hover:text-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 md:grid">
              <Bell className="size-4" aria-hidden="true" />
            </Link>
            <Link href="/settings#help" aria-label="도움말 보기" className="hidden size-10 place-items-center rounded-xl border border-border text-muted-foreground transition-colors hover:border-primary/30 hover:text-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 md:grid">
              <HelpCircle className="size-4" aria-hidden="true" />
            </Link>
            <Link href="/settings#profile" aria-label="프로필 메뉴" className="hidden h-10 items-center gap-2 rounded-xl border border-border bg-background/80 px-3 text-xs font-bold text-foreground transition-colors hover:border-primary/30 hover:text-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 xl:inline-flex">
              <UserCircle className="size-4 text-primary" aria-hidden="true" />
              Seongho
            </Link>
            <span className="hidden rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary xl:inline-flex">
              답장 추적
            </span>
            <span className="hidden rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-700 xl:inline-flex">
              충돌 조율
            </span>
          </div>
        </header>

        <section className="min-h-0 flex-1 overflow-hidden p-3 lg:p-4">
          {children}
        </section>
      </main>

      {isWorkspaceMenuOpen ? (
        <button
          type="button"
          aria-label="모바일 워크스페이스 메뉴 배경 닫기"
          data-testid="mobile-workspace-backdrop"
          popoverTarget="mobile-workspace-menu"
          popoverTargetAction="hide"
          onClick={closeMobileWorkspaceMenu}
          className="fixed inset-0 z-[70] bg-slate-950/75 backdrop-blur-sm xl:hidden"
        />
      ) : null}

      <div
        id="mobile-workspace-menu"
        popover="auto"
        role="dialog"
        aria-label="모바일 워크스페이스 메뉴"
        data-open={isWorkspaceMenuOpen ? 'true' : 'false'}
        onToggle={(event) => setIsWorkspaceMenuOpen(event.currentTarget.matches(':popover-open'))}
        className="fixed inset-y-0 left-0 z-[80] h-dvh w-[min(88vw,360px)] max-w-md overflow-y-auto overscroll-contain rounded-r-3xl border-r border-border bg-card/98 p-4 shadow-[0_24px_70px_rgba(15,23,42,0.22)] backdrop-blur-xl xl:hidden"
      >
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-sm font-black text-foreground">워크스페이스 메뉴</p>
            <p className="mt-1 text-xs text-muted-foreground">메일, 일정, 실행 항목, 데이터와 보안 메뉴로 이동합니다.</p>
          </div>
          <button
            type="button"
            aria-label="모바일 워크스페이스 메뉴 닫기"
            popoverTarget="mobile-workspace-menu"
            popoverTargetAction="hide"
            onClick={closeMobileWorkspaceMenu}
            className="grid size-10 place-items-center rounded-2xl border border-border bg-background text-sm font-black text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          >
            ×
          </button>
        </div>
        <div className="space-y-4">
          <section aria-label="Mobile startup preference" className="space-y-2">
            <p className="px-1 text-[11px] font-black text-muted-foreground">시작 화면</p>
            <div className="grid grid-cols-3 gap-2">
              {startupViewItems.map(({ label, view, description }) => {
                const active = startupView === view;
                return (
                  <button
                    key={view}
                    type="button"
                    data-startup-view={view}
                    aria-pressed={active}
                    title={description}
                    popoverTarget="mobile-workspace-menu"
                    popoverTargetAction="hide"
                    onClick={() => handleStartupViewChange(view)}
                    className={`min-h-11 rounded-2xl border px-2 text-xs font-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                      active ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background/70 text-foreground'
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </section>

          <nav aria-label="Mobile mail shortcuts" className="grid gap-2">
            <p className="px-1 text-[11px] font-black text-muted-foreground">메일</p>
            {mailNavItems.map(({ label, description, href, icon: Icon }) => {
              const active = isActivePath(pathname, href, '', searchParams);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => closeMobileWorkspaceMenu()}
                  className={`flex min-h-11 items-center gap-3 rounded-2xl border px-3 py-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                    active ? 'border-primary bg-primary text-primary-foreground' : 'border-border/70 bg-background/70 text-foreground'
                  }`}
                >
                  <Icon className="size-4" aria-hidden="true" />
                  <span className="flex flex-col leading-tight">
                    <span>{label}</span>
                    <span className="text-[11px] font-medium text-muted-foreground">{description}</span>
                  </span>
                </Link>
              );
            })}
          </nav>

          <nav aria-label="Mobile workspace shortcuts" className="grid gap-2">
            <p className="px-1 text-[11px] font-black text-muted-foreground">워크스페이스</p>
            {mobileWorkspaceMenuItems.map(({ label, description, href, icon: Icon, view }) => {
              const active = activeMobileView === view;
              return (
                <a
                  key={href}
                  href={href}
                  data-mobile-workspace-shortcut={view}
                  aria-current={active ? 'page' : undefined}
                  onClick={(event) => handleMobileWorkspaceChange(view, event)}
                  className={`flex min-h-11 items-center gap-3 rounded-2xl border px-3 py-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                    active ? 'border-primary bg-primary text-primary-foreground' : 'border-border/70 bg-background/70 text-foreground'
                  }`}
                >
                  <Icon className="size-4" aria-hidden="true" />
                  <span className="flex flex-col leading-tight">
                    <span>{label}</span>
                    <span className="text-[11px] font-medium text-muted-foreground">{description}</span>
                  </span>
                </a>
              );
            })}
          </nav>

          <nav aria-label="Mobile primary destinations" className="grid gap-2">
            <p className="px-1 text-[11px] font-black text-muted-foreground">주요 작업공간</p>
            {primaryNavItems.map(({ label, href, icon: Icon }) => {
              const active = isActivePath(pathname, href, '', searchParams);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => closeMobileWorkspaceMenu()}
                  className={`flex min-h-11 items-center gap-3 rounded-2xl border px-3 py-2 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                    active ? 'border-primary bg-primary text-primary-foreground' : 'border-border/70 bg-background/70 text-foreground'
                  }`}
                >
                  <Icon className="size-4" aria-hidden="true" />
                  <span>{label}</span>
                </Link>
              );
            })}
          </nav>

          <nav aria-label="Mobile utility menu" className="grid gap-2">
            <p className="px-1 text-[11px] font-black text-muted-foreground">도움</p>
            <Link
              href="/settings"
              onClick={() => closeMobileWorkspaceMenu()}
              className="flex min-h-11 items-center gap-3 rounded-2xl border border-border/70 bg-background/70 px-3 py-2 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              <Settings className="size-4 text-primary" aria-hidden="true" />
              <span className="flex flex-col leading-tight">
                <span>설정</span>
                <span className="text-[11px] font-medium text-muted-foreground">시작 화면과 계정 설정</span>
              </span>
            </Link>
            <Link
              href="/settings#help"
              onClick={() => closeMobileWorkspaceMenu()}
              className="flex min-h-11 items-center gap-3 rounded-2xl border border-border/70 bg-background/70 px-3 py-2 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              <HelpCircle className="size-4 text-primary" aria-hidden="true" />
              <span>도움말</span>
            </Link>
            <Link
              href="/settings#profile"
              onClick={() => closeMobileWorkspaceMenu()}
              className="flex min-h-11 items-center gap-3 rounded-2xl border border-border/70 bg-background/70 px-3 py-2 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              <UserCircle className="size-4 text-primary" aria-hidden="true" />
              <span>프로필</span>
            </Link>
          </nav>
        </div>
      </div>

      <nav aria-label="Mobile workspace sections" className="fixed inset-x-3 bottom-[calc(0.75rem+env(safe-area-inset-bottom))] z-[60] grid grid-cols-5 items-center rounded-3xl border border-border bg-card/95 p-2 shadow-[0_18px_50px_rgba(15,23,42,0.14)] backdrop-blur-xl lg:hidden">
        {mobileWorkspaceItems.slice(0, 2).map(({ label, icon: Icon, view }) => {
          const active = activeMobileView === view;
          return (
            <a
              href={`#mobile-${view}`}
              key={label}
              onClick={(event) => handleMobileWorkspaceChange(view, event)}
              data-mobile-view={view}
              aria-current={active ? 'page' : undefined}
              className={`flex min-h-11 flex-col items-center justify-center gap-1 rounded-2xl text-[11px] font-semibold text-center ${
                active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'
              }`}
            >
              <Icon className="size-4" aria-hidden="true" />
              {label}
            </a>
          );
        })}
        <button
          type="button"
          aria-label="판단 보조 빠른 실행"
          aria-haspopup="dialog"
          aria-controls="mobile-judgment-assist-action-menu"
          popoverTarget="mobile-judgment-assist-action-menu"
          className="mx-auto grid size-14 -translate-y-3 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-[0_18px_38px_rgba(37,99,255,0.35)] transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 active:translate-y-[-10px]"
        >
          <Sparkles className="size-6" aria-hidden="true" />
        </button>
        {mobileWorkspaceItems.slice(2).map(({ label, icon: Icon, view }) => {
          const active = activeMobileView === view;
          return (
            <a
              href={`#mobile-${view}`}
              key={label}
              onClick={(event) => handleMobileWorkspaceChange(view, event)}
              data-mobile-view={view}
              aria-current={active ? 'page' : undefined}
              className={`flex min-h-11 flex-col items-center justify-center gap-1 rounded-2xl text-center text-[11px] font-semibold ${
                active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'
              }`}
            >
              <Icon className="size-4" aria-hidden="true" />
              {label}
            </a>
          );
        })}
      </nav>
      <div
        id="mobile-judgment-assist-action-menu"
        role="dialog"
        aria-label="판단 보조 빠른 실행 메뉴"
        popover="auto"
        className="fixed inset-x-5 bottom-[calc(6rem+env(safe-area-inset-bottom))] z-[70] max-h-[calc(100dvh-8rem-env(safe-area-inset-bottom))] overflow-y-auto overscroll-contain rounded-3xl border border-border bg-card/98 p-4 shadow-[0_24px_70px_rgba(15,23,42,0.2)] backdrop:bg-transparent lg:hidden"
      >
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-black text-foreground">판단 보조 빠른 실행</p>
              <p className="mt-1 text-xs text-muted-foreground">메일 맥락을 바로 실행으로 전환합니다.</p>
            </div>
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-bold text-primary">Naruon 판단 보조</span>
          </div>
          <div className="grid gap-2">
            {headerActions.map(({ label, action, icon: Icon, message }) => (
              <button
                key={action}
                type="button"
                data-mobile-quick-action={action}
                popoverTarget="mobile-judgment-assist-action-menu"
                popoverTargetAction="hide"
                onClick={() => handleHeaderAction(action)}
                className="flex min-h-12 items-center gap-3 rounded-2xl border border-border/80 bg-background/80 px-3 py-2 text-left text-sm font-bold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              >
                <Icon className="size-4 text-primary" aria-hidden="true" />
                <span className="flex flex-col leading-tight">
                  {label}
                  <span className="text-[11px] font-medium text-muted-foreground">{message}</span>
                </span>
              </button>
            ))}
          </div>
      </div>
    </div>
  );
}
