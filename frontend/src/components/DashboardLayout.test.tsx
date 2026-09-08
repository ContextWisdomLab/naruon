/* @vitest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

import { DashboardLayout } from "./DashboardLayout";

function setInputValue(input: HTMLInputElement, value: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  )?.set;
  valueSetter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("DashboardLayout", () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    vi.useRealTimers();
    if (root) {
      act(() => root?.unmount());
    }
    root = null;
    container?.remove();
    container = null;
    localStorage.clear();
    window.history.replaceState(null, "", "/");
    Reflect.deleteProperty(window, "__naruonMobileWorkspace");
  });

  it("keeps the active desktop destination inside the navigation inset", () => {
    vi.useFakeTimers();
    window.history.replaceState(null, "", "/search");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(
        <DashboardLayout>
          <section>Search workspace content</section>
        </DashboardLayout>,
      );
    });

    const primaryNav = container.querySelector<HTMLElement>(
      'nav[aria-label="Primary workspace navigation"]',
    );
    const activeLink = container.querySelector<HTMLAnchorElement>('a[href="/search"]');
    vi.spyOn(primaryNav!, "getBoundingClientRect").mockReturnValue({
      left: 0,
      right: 100,
    } as DOMRect);
    vi.spyOn(activeLink!, "getBoundingClientRect").mockReturnValue({
      left: 90,
      right: 110,
    } as DOMRect);
    act(() => {
      vi.runOnlyPendingTimers();
    });
    expect(primaryNav?.scrollLeft).toBe(26);
    expect(
      container.querySelector<HTMLAnchorElement>('a[href="/search"]')
        ?.getAttribute("aria-current"),
    ).toBe("page");
  });

  it("restores active destination visibility after the desktop navigation narrows", () => {
    vi.useFakeTimers();
    window.history.replaceState(null, "", "/search");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(
        <DashboardLayout>
          <section>Search workspace content</section>
        </DashboardLayout>,
      );
    });

    const primaryNav = container.querySelector<HTMLElement>(
      'nav[aria-label="Primary workspace navigation"]',
    );
    const activeLink = container.querySelector<HTMLAnchorElement>('a[href="/search"]');
    vi.spyOn(primaryNav!, "getBoundingClientRect").mockReturnValue({
      left: 0,
      right: 100,
    } as DOMRect);
    const activeLinkRect = vi
      .spyOn(activeLink!, "getBoundingClientRect")
      .mockReturnValue({ left: 20, right: 60 } as DOMRect);
    act(() => {
      vi.runOnlyPendingTimers();
    });
    expect(primaryNav?.scrollLeft).toBe(0);

    activeLinkRect.mockReturnValue({ left: 90, right: 110 } as DOMRect);
    act(() => {
      window.dispatchEvent(new Event("resize"));
      vi.runOnlyPendingTimers();
    });

    expect(primaryNav?.scrollLeft).toBe(26);
  });

  it("renders the Naruon branded shell with accessible navigation landmarks", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(
        <DashboardLayout>
          <section>Inbox workspace content</section>
        </DashboardLayout>,
      );
    });

    const banner = container.querySelector('header[aria-label="Naruon workspace header"]');
    const primaryNav = container.querySelector('nav[aria-label="Primary workspace navigation"]');
    const mobileNav = container.querySelector('nav[aria-label="Mobile workspace sections"]');
    const mobileQuickActionButton = container.querySelector<HTMLButtonElement>('button[aria-label="판단 보조 빠른 실행"]');
    const mobileMenuButton = container.querySelector<HTMLButtonElement>('button[aria-label="워크스페이스 메뉴 열기"]');
    const mobileNavLinks = Array.from(mobileNav?.querySelectorAll('a') ?? []).map(
      (link) => link.textContent,
    );
    const headerActionButtons = Array.from(
      banner?.querySelectorAll<HTMLButtonElement>('button[data-header-action]') ?? [],
    ).map((button) => button.textContent);
    const headerActionGroup = banner?.querySelector<HTMLElement>('[data-testid="header-action-group"]');
    const main = container.querySelector("main#main-content");
    const skipLink = container.querySelector<HTMLAnchorElement>(
      'a[href="#main-content"]',
    );
    const logo = container.querySelector<HTMLImageElement>('img[alt="Naruon"]');
    const globalSearchInput = container.querySelector<HTMLInputElement>("#global-search-input");

    expect(banner).not.toBeNull();
    expect(primaryNav?.textContent).toContain("홈");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/mail"]')?.textContent).toContain("메일");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/calendar"]')?.textContent).toContain("일정");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/tasks"]')?.textContent).toContain("작업");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/projects"]')?.textContent).toContain("프로젝트");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/search"]')?.textContent).toContain("맥락 검색");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/ai-hub"]')?.textContent).toContain("AI 허브");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/data"]')?.textContent).toContain("데이터");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/security"]')?.textContent).toContain("보안");
    expect(primaryNav?.querySelector<HTMLAnchorElement>('a[href="/settings"]')?.textContent).toContain("설정");
    expect(mobileNav).not.toBeNull();
    expect(banner?.querySelector<HTMLAnchorElement>('a[aria-label="알림 보기"]')?.getAttribute("href")).toBe("/security");
    expect(banner?.querySelector<HTMLAnchorElement>('a[aria-label="도움말 보기"]')?.getAttribute("href")).toBe("/settings#help");
    expect(banner?.querySelector<HTMLAnchorElement>('a[aria-label="프로필 메뉴"]')?.getAttribute("href")).toBe("/settings#profile");
    expect(mobileMenuButton?.getAttribute("aria-expanded")).toBe("false");
    expect(mobileMenuButton?.getAttribute("aria-controls")).toBe("mobile-workspace-menu");
    expect(mobileNavLinks).toEqual(["받은편지함", "맥락 검색", "일정", "더보기"]);
    expect(mobileQuickActionButton).not.toBeNull();
    expect(mobileQuickActionButton?.getAttribute("popovertarget")).toBe("mobile-judgment-assist-action-menu");
    expect(mobileQuickActionButton?.getAttribute("aria-haspopup")).toBe("dialog");
    expect(container.textContent).not.toContain("준비 중");
    expect(main).not.toBeNull();
    expect(skipLink).not.toBeNull();
    expect(logo?.getAttribute("src")).toBe("/brand/naruon-symbol.svg");
    expect(globalSearchInput?.getAttribute("type")).toBe("search");
    expect(globalSearchInput?.getAttribute("inputmode")).toBe("search");
    expect(globalSearchInput?.getAttribute("role")).toBe("searchbox");
    expect(headerActionButtons).toEqual(["일정 반영", "답장 초안", "실행 항목 생성"]);
    expect(headerActionGroup?.className).toContain("lg:flex");
    expect(headerActionGroup?.className).not.toContain("xl:flex");
    expect(skipLink?.textContent).toBe("본문 바로가기");
    expect(skipLink?.className).toContain("focus:right-4");
    expect(skipLink?.className).toContain("focus:text-center");
    expect(main?.textContent ?? "").toContain("Inbox workspace content");

    const headerEvents: string[] = [];
    const onHeaderAction: EventListener = (event) => {
      headerEvents.push((event as CustomEvent<{ action: string }>).detail.action);
    };
    window.addEventListener("naruon:header-action", onHeaderAction);

    act(() => {
      banner?.querySelector<HTMLButtonElement>('button[data-header-action="reply-draft"]')?.click();
    });

    expect(headerEvents).toContain("reply-draft");

    const desktopStartupPreference = container.querySelector<HTMLElement>('section[aria-label="Desktop startup preference"]');
    expect(desktopStartupPreference).not.toBeNull();
    expect(desktopStartupPreference?.textContent ?? "").toContain("시작 화면");
    expect(desktopStartupPreference?.querySelector<HTMLButtonElement>('button[data-desktop-startup-view="dashboard"]')?.textContent).toContain("홈");
    expect(desktopStartupPreference?.querySelector<HTMLButtonElement>('button[data-desktop-startup-view="email"]')?.textContent).toContain("메일");
    expect(desktopStartupPreference?.querySelector<HTMLButtonElement>('button[data-desktop-startup-view="calendar"]')?.textContent).toContain("일정");

    act(() => {
      desktopStartupPreference?.querySelector<HTMLButtonElement>('button[data-desktop-startup-view="email"]')?.click();
    });

    expect(localStorage.getItem("naruon_startup_view")).toBe("email");
    expect(window.location.hash).toBe("");

    act(() => {
      mobileMenuButton?.click();
    });

    expect(mobileMenuButton?.getAttribute("aria-expanded")).toBe("true");
    const mobileMenu = container.querySelector<HTMLElement>('#mobile-workspace-menu');
    expect(container.querySelector('[data-testid="mobile-workspace-backdrop"]')).not.toBeNull();
    expect(mobileMenu?.className).toContain("inset-y-0");
    expect(mobileMenu?.querySelector<HTMLButtonElement>('button[aria-label="모바일 워크스페이스 메뉴 닫기"]')).not.toBeNull();
    expect(mobileMenu?.textContent ?? "").toContain("시작 화면");
    expect(mobileMenu?.textContent ?? "").toContain("홈");
    expect(mobileMenu?.textContent ?? "").toContain("메일");
    expect(mobileMenu?.textContent ?? "").toContain("일정");
    expect(mobileMenu?.textContent ?? "").toContain("메일");
    expect(mobileMenu?.textContent ?? "").toContain("워크스페이스");
    expect(mobileMenu?.textContent ?? "").toContain("주요 작업공간");
    expect(mobileMenu?.textContent ?? "").toContain("도움");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/"]')?.textContent).toContain("홈");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/mail"]')?.textContent).toContain("메일");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/mail?folder=inbox"]')?.textContent).toContain("받은 메일");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/mail?folder=sent"]')?.textContent).toContain("보낸 메일");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/calendar"]')?.textContent).toContain("일정");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/tasks"]')?.textContent).toContain("작업");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/projects"]')?.textContent).toContain("프로젝트");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/search"]')?.textContent).toContain("맥락 검색");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/ai-hub"]')?.textContent).toContain("AI 허브");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/data"]')?.textContent).toContain("데이터");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/security"]')?.textContent).toContain("보안");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/settings"]')?.textContent).toContain("설정");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/settings#help"]')?.textContent).toContain("도움말");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="/settings#profile"]')?.textContent).toContain("프로필");
    expect(mobileMenu?.querySelector<HTMLAnchorElement>('a[href="#mobile-calendar"]')?.textContent).toContain("일정");
    expect(mobileMenu?.querySelector<HTMLButtonElement>('button[data-startup-view="calendar"]')).not.toBeNull();

    act(() => {
      mobileMenu?.querySelector<HTMLButtonElement>('button[data-startup-view="calendar"]')?.click();
    });

    expect(localStorage.getItem("naruon_startup_view")).toBe("calendar");
    expect(window.location.hash).toBe("");
    expect(mobileMenuButton?.getAttribute("aria-expanded")).toBe("false");

    act(() => {
      mobileMenuButton?.click();
    });
    act(() => {
      mobileMenu?.querySelector<HTMLButtonElement>('button[aria-label="모바일 워크스페이스 메뉴 닫기"]')?.click();
    });
    expect(mobileMenuButton?.getAttribute("aria-expanded")).toBe("false");

    const events: string[] = [];
    const onMobileWorkspace: EventListener = (event) => {
      events.push((event as CustomEvent<{ view: string }>).detail.view);
    };
    window.addEventListener("naruon:mobile-workspace", onMobileWorkspace);

    act(() => {
      mobileQuickActionButton?.click();
    });

    expect(container.querySelector('#mobile-judgment-assist-action-menu')?.textContent ?? "").toContain("답장 초안");

    act(() => {
      container?.querySelector<HTMLButtonElement>('button[data-mobile-quick-action="create-task"]')?.click();
    });

    expect(headerEvents).toContain("create-task");

    const actionsNavLink = mobileNav?.querySelector<HTMLAnchorElement>('[data-mobile-view="actions"]');
    const actionsClick = new MouseEvent("click", { bubbles: true, cancelable: true });
    act(() => {
      actionsNavLink?.dispatchEvent(actionsClick);
    });

    expect(actionsClick.defaultPrevented).toBe(true);
    expect(events).toContain("actions");
    window.removeEventListener("naruon:header-action", onHeaderAction);
    window.removeEventListener("naruon:mobile-workspace", onMobileWorkspace);
  });

  it("clears and refocuses the desktop global search without native search controls", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(
        <DashboardLayout>
          <section>Dashboard workspace content</section>
        </DashboardLayout>,
      );
    });

    const input = container.querySelector<HTMLInputElement>("#global-search-input");
    expect(input).not.toBeNull();
    expect(input?.getAttribute("type")).toBe("search");
    expect(input?.getAttribute("inputmode")).toBe("search");
    expect(input?.getAttribute("role")).toBe("searchbox");

    act(() => {
      setInputValue(input as HTMLInputElement, "계약 검토");
    });

    const clearButton = container.querySelector<HTMLButtonElement>(
      'button[aria-label="맥락 검색어 지우기"]',
    );
    expect(clearButton).not.toBeNull();

    act(() => {
      clearButton?.click();
    });

    expect(input?.value).toBe("");
    expect(document.activeElement).toBe(input);
  });

  it("keeps desktop primary and mobile primary destinations synchronized", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(
        <DashboardLayout>
          <section>Inbox workspace content</section>
        </DashboardLayout>,
      );
    });

    const desktopHrefs = Array.from(
      container.querySelectorAll<HTMLAnchorElement>('nav[aria-label="Primary workspace navigation"] a'),
    ).map((link) => link.getAttribute("href"));
    const mobileHrefs = Array.from(
      container.querySelectorAll<HTMLAnchorElement>('nav[aria-label="Mobile primary destinations"] a'),
    ).map((link) => link.getAttribute("href"));

    expect(mobileHrefs).toEqual(desktopHrefs);
    expect(mobileHrefs).toEqual(["/", "/mail", "/calendar", "/tasks", "/projects", "/search", "/ai-hub", "/data", "/security", "/settings"]);
  });

  it("keeps query-based mail shortcuts mutually exclusive in the mobile drawer", () => {
    window.history.replaceState(null, "", "/mail?folder=sent");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(
        <DashboardLayout>
          <section>Mail workspace content</section>
        </DashboardLayout>,
      );
    });

    act(() => {
      container
        ?.querySelector<HTMLButtonElement>('button[aria-label="워크스페이스 메뉴 열기"]')
        ?.click();
    });

    const mobileMenu = container.querySelector<HTMLElement>('#mobile-workspace-menu');
    expect(
      mobileMenu
        ?.querySelector<HTMLAnchorElement>('a[href="/mail?folder=sent"]')
        ?.getAttribute("aria-current"),
    ).toBe("page");
    expect(
      mobileMenu
        ?.querySelector<HTMLAnchorElement>('a[href="/mail?folder=inbox"]')
        ?.getAttribute("aria-current"),
    ).toBeNull();
    expect(
      mobileMenu
        ?.querySelector<HTMLAnchorElement>('a[href="/mail?folder=starred"]')
        ?.getAttribute("aria-current"),
    ).toBeNull();
  });

  it("clears stale mobile hashes and resets the mobile workspace store when switching startup back to dashboard", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root?.render(
        <DashboardLayout>
          <section>Inbox workspace content</section>
        </DashboardLayout>,
      );
    });

    const mobileMenuButton = container.querySelector<HTMLButtonElement>('button[aria-label="워크스페이스 메뉴 열기"]');
    act(() => {
      mobileMenuButton?.click();
    });
    const mobileMenu = container.querySelector<HTMLElement>('#mobile-workspace-menu');

    window.history.replaceState(null, "", "/#mobile-actions");

    act(() => {
      mobileMenu?.querySelector<HTMLButtonElement>('button[data-startup-view="calendar"]')?.click();
    });

    expect(localStorage.getItem("naruon_startup_view")).toBe("calendar");
    expect(window.location.hash).toBe("");
    expect(window.__naruonMobileWorkspace?.view).toBe("calendar");
    expect(container.querySelector<HTMLAnchorElement>('[data-mobile-view="calendar"]')?.getAttribute("aria-current")).toBe("page");

    act(() => {
      mobileMenu?.querySelector<HTMLButtonElement>('button[data-startup-view="dashboard"]')?.click();
    });

    expect(localStorage.getItem("naruon_startup_view")).toBe("dashboard");
    expect(window.location.hash).toBe("");
    expect(window.__naruonMobileWorkspace?.view).toBe("inbox");
    expect(container.querySelector<HTMLAnchorElement>('[data-mobile-view="inbox"]')?.getAttribute("aria-current")).toBe("page");
    expect(container.querySelector<HTMLAnchorElement>('[data-mobile-view="calendar"]')?.getAttribute("aria-current")).toBeNull();
  });

});
