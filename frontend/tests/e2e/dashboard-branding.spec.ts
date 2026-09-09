import { expect, test } from '@playwright/test';

import { mockDashboardApi } from './helpers';

function e2eSessionToken(payload: Record<string, unknown>) {
  const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.signature`;
}

function expectBrowserCookieSession(headers: Record<string, string> | undefined, token: string) {
  expect(headers?.authorization).toBeUndefined();
  expect(headers?.cookie ?? '').toContain(`naruon_session=${token}`);
}

test('renders the desktop Naruon shell with local brand assets', async ({ page }) => {
  const requestedUrls: string[] = [];
  page.on('request', (request) => requestedUrls.push(request.url()));
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);

  await page.goto('/');

  await expect(page.getByRole('img', { name: 'Naruon' })).toBeVisible();
  // Sidebars and extra navigations were removed to match the unified top header branding.
  const header = page.locator('header[aria-label="Naruon workspace header"]');
  const primaryNav = page.getByRole('navigation', { name: 'Primary workspace navigation' });
  await expect(primaryNav).toBeVisible();
  await expect(primaryNav.getByRole('link', { name: '홈', exact: true })).toHaveAttribute('href', '/');
  await expect(primaryNav.getByRole('link', { name: '메일', exact: true })).toHaveAttribute('href', '/mail');
  await expect(primaryNav.getByRole('link', { name: '일정', exact: true })).toHaveAttribute('href', '/calendar');
  await expect(primaryNav.getByRole('link', { name: '작업', exact: true })).toHaveAttribute('href', '/tasks');
  await expect(primaryNav.getByRole('link', { name: '프로젝트', exact: true })).toHaveAttribute('href', '/projects');
  await expect(primaryNav.getByRole('link', { name: '맥락 검색', exact: true })).toHaveAttribute('href', '/search');
  await expect(primaryNav.getByRole('link', { name: 'AI 허브', exact: true })).toHaveAttribute('href', '/ai-hub');
  await expect(primaryNav.getByRole('link', { name: '데이터', exact: true })).toHaveAttribute('href', '/data');
  await expect(primaryNav.getByRole('link', { name: '보안', exact: true })).toHaveAttribute('href', '/security');
  await expect(primaryNav.getByRole('link', { name: '설정', exact: true })).toHaveAttribute('href', '/settings');
  await expect(header.getByRole('link', { name: '알림 보기' })).toHaveAttribute('href', '/security');
  await expect(header.getByRole('link', { name: '도움말 보기' })).toHaveAttribute('href', '/settings#help');
  await expect(header.getByRole('link', { name: '프로필 메뉴' })).toHaveAttribute('href', '/settings#profile');
  await expect(header.getByRole('button', { name: '일정 반영' })).toBeVisible();
  await expect(header.getByRole('button', { name: '답장 초안' })).toBeVisible();
  await expect(header.getByRole('button', { name: '실행 항목 생성' })).toBeVisible();
  await header.getByRole('button', { name: '답장 초안' }).click();
  await expect(header.getByText('메일 상세 패널에서 답장 초안을 생성합니다.')).toBeVisible();
  await expect(header.getByText('메일 상세 패널에서 답장 초안을 생성합니다.')).toBeVisible();
  await expect(header.getByText('메일 상세 패널에서 답장 초안을 생성합니다.')).toBeVisible();

  await expect(page.getByRole('region', { name: '홈 개요' }).first()).toBeVisible();
  const homeQuickActions = page.getByLabel('홈 빠른 실행');
  await expect(homeQuickActions.getByRole('link', { name: '메일함 열기' })).toHaveAttribute('href', '/mail');
  await expect(homeQuickActions.getByRole('link', { name: '보낸 메일 답변 추적' })).toHaveAttribute('href', '/mail?folder=sent');
  await expect(homeQuickActions.getByRole('link', { name: '일정 후보 검토' })).toHaveAttribute('href', '/calendar');
  await expect(homeQuickActions.getByRole('link', { name: '실행 항목 보드' })).toHaveAttribute('href', '/tasks');
  await expect(page.getByRole('button', { name: '메일함 바로가기' }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: '일정 확인하기' }).first()).toBeVisible();
  await page.getByRole('button', { name: '메일함 바로가기' }).first().click();
  const desktopWorkspace = page.getByRole('region', { name: '데스크톱 메일 작업공간' });
  await expect(desktopWorkspace.getByText('메일을 선택하세요')).toBeVisible();
  await expect(page).not.toHaveURL(/#mobile-detail$/);

  const desktopStartup = page.getByRole('region', { name: 'Desktop startup preference' });
  await expect(desktopStartup).toBeVisible();
  await expect(desktopStartup.getByRole('button', { name: '홈' })).toBeVisible();
  await expect(desktopStartup.getByRole('button', { name: '메일' })).toBeVisible();
  await expect(desktopStartup.getByRole('button', { name: '일정' })).toBeVisible();

  expect(
    requestedUrls.some((url) => {
      const hostname = new URL(url).hostname;
      return hostname === 'fonts.googleapis.com' || hostname === 'fonts.gstatic.com';
    }),
  ).toBe(false);
  await expect(page.locator('link[rel="preload"][href="/brand/naruon-logo.svg"]')).toHaveCount(0);
});

test('renders Today dashboard pending reply lane with signed API headers', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-dashboard.pending-replies.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  const desktopPendingRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/emails/pending-replies' && request.method() === 'GET';
  });

  await page.goto('/');
  const desktopHeaders = (await desktopPendingRequest).headers();
  expectBrowserCookieSession(desktopHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(desktopHeaders[headerName]).toBeUndefined();
  }

  const desktopDashboard = page.locator('section[aria-label="홈 개요"]:visible').first();
  await expect(desktopDashboard).toBeVisible();
  await expect(page.getByRole('article', { name: '답변 대기' }).first()).toBeVisible();
  await expect(desktopDashboard.getByText('답변 대기 메일')).toBeVisible();
  await expect(desktopDashboard.getByText('벤더 계약 답변 요청')).toBeVisible();
  await expect(desktopDashboard.getByText('예산 승인 후속 확인')).toBeVisible();
  const desktopEscalationRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/tasks/reply-sla-escalations' && request.method() === 'POST';
  });
  await desktopDashboard.getByRole('button', { name: '홈에서 보낸 메일 미답변 팔로업 작업 생성' }).click();
  const desktopEscalationHeaders = (await desktopEscalationRequest).headers();
  expectBrowserCookieSession(desktopEscalationHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(desktopEscalationHeaders[headerName]).toBeUndefined();
  }
  await expect(desktopDashboard.getByText('1개 팔로업 작업 생성, 2개 답변 대기 확인')).toBeVisible();
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('today-pending-replies-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  const mobilePendingRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/emails/pending-replies' && request.method() === 'GET';
  });
  await page.goto('/');
  expectBrowserCookieSession((await mobilePendingRequest).headers(), expectedNaruonToken);
  const mobileDashboard = page.locator('section[aria-label="홈 개요"]:visible').first();
  await expect(mobileDashboard).toBeVisible();
  await mobileDashboard.getByText('답변 대기 메일').scrollIntoViewIfNeeded();
  await expect(mobileDashboard.getByText('답변 대기 메일')).toBeVisible();
  await expect(mobileDashboard.getByText('벤더 계약 답변 요청')).toBeVisible();
  const mobileEscalationRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/tasks/reply-sla-escalations' && request.method() === 'POST';
  });
  await mobileDashboard.getByRole('button', { name: '홈에서 보낸 메일 미답변 팔로업 작업 생성' }).click();
  const mobileEscalationHeaders = (await mobileEscalationRequest).headers();
  expectBrowserCookieSession(mobileEscalationHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(mobileEscalationHeaders[headerName]).toBeUndefined();
  }
  await expect(mobileDashboard.getByText('1개 팔로업 작업 생성, 2개 답변 대기 확인')).toBeVisible();
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('today-pending-replies-mobile-pending-list.png'), fullPage: false });
  const dashboardScrollMetrics = await mobileDashboard.evaluate((scroller) => {
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(dashboardScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(dashboardScrollMetrics.after).toBeGreaterThan(dashboardScrollMetrics.before);
  await page.screenshot({ path: testInfo.outputPath('today-pending-replies-mobile-scroll.png'), fullPage: false });
});

test('keeps the short mobile AI quick action menu inside the viewport with scrollable actions', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 640 });
  await mockDashboardApi(page);

  await page.goto('/');
  await page.getByRole('button', { name: 'AI 빠른 실행' }).click();

  const menu = page.getByRole('dialog', { name: 'AI 빠른 실행 메뉴' });
  await expect(menu).toBeVisible();
  await expect(menu.getByRole('button', { name: '실행 항목 생성' })).toBeVisible();
  const bounds = await menu.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    return { top: rect.top, bottom: rect.bottom, viewportHeight: window.innerHeight, overflowY: style.overflowY };
  });
  expect(bounds.top).toBeGreaterThanOrEqual(0);
  expect(bounds.bottom).toBeLessThanOrEqual(bounds.viewportHeight);
  expect(['auto', 'scroll']).toContain(bounds.overflowY);
});

test('renders compact mobile navigation without hover-only controls', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDashboardApi(page);

  await page.goto('/#mobile-detail');

  await expect(page.getByRole('region', { name: '모바일 받은편지함' })).toBeVisible();

  await expect(page.getByRole('navigation', { name: 'Mobile workspace sections' })).toBeVisible();
  await expect(page.getByRole('link', { name: '받은편지함' })).toBeVisible();
  await expect(page.getByRole('link', { name: '맥락 검색' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI 빠른 실행' })).toBeVisible();
  await expect(page.getByRole('link', { name: '일정' })).toBeVisible();
  await expect(page.getByRole('link', { name: '더보기' })).toBeVisible();
  await expect(page.getByRole('button', { name: '워크스페이스 메뉴 열기' })).toBeVisible();

  const mobileAiButton = page.getByRole('button', { name: 'AI 빠른 실행' });
  await mobileAiButton.click();
  await expect(page.getByRole('dialog', { name: 'AI 빠른 실행 메뉴' })).toBeVisible();
  await expect(page.getByRole('button', { name: '답장 초안' })).toBeVisible();
  await page.getByRole('link', { name: '더보기' }).click();
  await expect(page.getByRole('region', { name: '모바일 AI 실행' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '관계 맥락' })).toBeVisible();

  await page.getByRole('link', { name: '맥락 검색' }).click();
  await expect(page.getByRole('region', { name: '모바일 맥락 검색' })).toBeVisible();
  await expect(page.getByText('메일, 첨부, 일정, 사람을 한 번에 검색합니다.')).toBeVisible();

  await page.getByRole('link', { name: '일정' }).click();
  await expect(page.getByRole('region', { name: '모바일 일정 연결' })).toBeVisible();
  await expect(page.getByText('일정 반영 대기')).toBeVisible();
});

const responsiveViewports = [
  { name: 'short mobile', width: 390, height: 640 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet portrait', width: 768, height: 1024 },
  { name: 'tablet landscape', width: 1024, height: 768 },
  { name: 'desktop', width: 1280, height: 1024 },
  { name: 'wide desktop', width: 1920, height: 1080 },
] as const;

for (const viewport of responsiveViewports) {
  test(`keeps the branded workspace usable without horizontal overflow at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockDashboardApi(page);

    await page.goto('/');

    await expect(page.locator('main#main-content')).toBeVisible();
    await expect(page.locator('header[aria-label="Naruon workspace header"]')).toBeVisible();
    await expect(page.getByRole('region', { name: '홈 개요' }).first()).toBeVisible();
    if (viewport.width <= 390) {
      const metricLabel = page
        .getByRole('article', { name: '받은 메일' })
        .first()
        .getByText('받은 메일', { exact: true });
      await expect(metricLabel).toBeVisible();
      const metricLabelBox = await metricLabel.boundingBox();
      expect(metricLabelBox).not.toBeNull();
      if (!metricLabelBox) throw new Error('Metric label bounding box was unavailable.');
      expect(metricLabelBox.height).toBeLessThan(48);
    }
    await page.getByRole('button', { name: '메일함 바로가기' }).first().click();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);

    if (viewport.width < 1024) {
      await expect(page.getByRole('navigation', { name: 'Mobile workspace sections' })).toBeVisible();
      await expect(page.getByRole('button', { name: '워크스페이스 메뉴 열기' })).toBeVisible();
      await expect(page.getByRole('region', { name: '모바일 받은편지함' })).toBeVisible();
    } else if (viewport.width < 1280) {
      await expect(page.getByRole('button', { name: '워크스페이스 메뉴 열기' })).toBeVisible();
      await page.getByRole('button', { name: '워크스페이스 메뉴 열기' }).click();
      const menu = page.getByRole('dialog', { name: '모바일 워크스페이스 메뉴' });
      await expect(menu.getByRole('link', { name: '메일', exact: true })).toHaveAttribute('href', '/mail');
      await expect(menu.getByRole('link', { name: /보낸 메일/ })).toHaveAttribute('href', '/mail?folder=sent');
      await expect(menu.getByRole('link', { name: '맥락 검색', exact: true })).toHaveAttribute('href', '/search');
      await menu.getByRole('button', { name: '모바일 워크스페이스 메뉴 닫기' }).click();
      await expect(page.getByRole('region', { name: '태블릿 메일 작업공간' })).toBeVisible();
      await expect(page.getByRole('region', { name: '데스크톱 메일 작업공간' })).toBeHidden();
      await expect(page.getByText('태블릿 맥락 패널')).toBeVisible();
      await expect(page.getByRole('button', { name: '일정 반영' })).toBeVisible();
      await expect(page.getByRole('button', { name: '답장 초안' })).toBeVisible();
      await expect(page.getByRole('button', { name: '실행 항목 생성' })).toBeVisible();
    } else {
      await expect(page.getByRole('navigation', { name: 'Primary workspace navigation' })).toBeVisible();
      await expect(page.getByRole('region', { name: '데스크톱 메일 작업공간' })).toBeVisible();
    }
  });
}

for (const destination of [
  { path: '/mail', heading: '메일을 선택하세요', marker: { name: '받은편지함' } },
  { path: '/calendar', heading: '일정 관리', marker: { text: '고객 원본 일정 반영 의도' } },
  { path: '/tasks', heading: '실행 항목 추적', marker: { name: '리소스 배정 검토 회의' } },
  { path: '/data', heading: '데이터와 파일', marker: { text: '중복 메일 스레드 정리 의도' } },
  { path: '/search', heading: '맥락 검색', marker: { name: '관계 맥락과 타임라인' } },
  { path: '/security', heading: '보안과 관리자', marker: { text: '원본 연결 RBAC / ABAC' } },
  { path: '/projects', heading: '프로젝트 워크스페이스', marker: { name: '의사결정 로그' } },
  { path: '/ai-hub', heading: 'AI 허브', marker: { name: '실행 항목' } },
  { path: '/settings', heading: '설정', marker: { name: '워크스페이스 설정' } },
] as const) {
  test(`renders the ${destination.path} workspace destination without horizontal overflow`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1024 });
    await mockDashboardApi(page);

    await page.goto(destination.path);

    await expect(page.getByRole('heading', { name: destination.heading, exact: true })).toBeVisible();
    if ('name' in destination.marker) {
      await expect(page.getByRole('heading', { name: destination.marker.name }).first()).toBeVisible();
    } else {
      await expect(page.getByText(destination.marker.text)).toBeVisible();
    }
    await expect(page.getByRole('navigation', { name: 'Primary workspace navigation' })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

test('renders source-backed Projects workspace with signed API headers and mobile scroll', async ({ page }, testInfo) => {
  const expectedNaruonToken = e2eSessionToken({ sub: 'alice', org: 'org-acme', workspace: 'workspace-org-acme' });
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  await page.setViewportSize({ width: 1280, height: 1024 });
  const desktopFoldersRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/webdav/folders' && request.method() === 'GET';
  });
  const desktopTasksRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/tasks' && request.method() === 'GET';
  });
  await page.goto('/projects');
  for (const request of [await desktopFoldersRequest, await desktopTasksRequest]) {
    const headers = request.headers();
    expectBrowserCookieSession(headers, expectedNaruonToken);
    for (const headerName of publicIdentityHeaders) {
      expect(headers[headerName]).toBeUndefined();
    }
  }

  await expect(page.getByRole('heading', { name: '프로젝트 워크스페이스' })).toBeVisible();
  await expect(page.getByText('Naruon Roadmap 2026').first()).toBeVisible();
  await expect(page.getByText('webdav_folder_roadmap')).toHaveCount(0);
  await expect(page.getByText('provider_write_executed=false')).toHaveCount(0);
  await expect(page.getByText('상태: 연결 준비').first()).toBeVisible();
  await expect(page.getByText('리소스 배정 검토 회의').first()).toBeVisible();
  await expect(page.getByText('외부 저장소 쓰기는 별도 승인 전까지 실행하지 않습니다.').first()).toBeVisible();
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('projects-source-backed-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileFoldersRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/webdav/folders' && request.method() === 'GET';
  });
  await page.goto('/projects');
  expectBrowserCookieSession((await mobileFoldersRequest).headers(), expectedNaruonToken);
  await expect(page.getByRole('heading', { name: '프로젝트 워크스페이스' })).toBeVisible();
  await page.getByRole('heading', { name: '연결 작업' }).scrollIntoViewIfNeeded();
  await expect(page.getByText('첨부파일 WebDAV 폴더 정리')).toBeVisible();
  const mobileScrollMetrics = await page.getByRole('region', { name: '프로젝트 내용' }).evaluate((scroller) => {
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(mobileScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(mobileScrollMetrics.after).toBeGreaterThan(mobileScrollMetrics.before);
  await page.screenshot({ path: testInfo.outputPath('projects-source-backed-mobile-scroll.png'), fullPage: false });

  await page.getByRole('button', { name: '워크스페이스 메뉴 열기' }).click();
  const menu = page.getByRole('dialog', { name: '모바일 워크스페이스 메뉴' });
  await menu.getByRole('link', { name: '프로젝트', exact: true }).scrollIntoViewIfNeeded();
  await expect(menu.getByRole('link', { name: '프로젝트', exact: true })).toHaveAttribute('href', '/projects');
  await expect(menu.getByRole('link', { name: '데이터', exact: true })).toHaveAttribute('href', '/data');
  await page.screenshot({ path: testInfo.outputPath('projects-source-backed-mobile-menu.png'), fullPage: false });
});

test('renders Security governance access audit sharing and policy with signed API headers', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-security.governance-e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  await page.setViewportSize({ width: 1280, height: 1024 });
  const accessRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/security/access-surface' && request.method() === 'GET';
  });
  await page.goto('/security');
  const accessHeaders = (await accessRequest).headers();
  expectBrowserCookieSession(accessHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(accessHeaders[headerName]).toBeUndefined();
  }

  await expect(page.getByRole('heading', { name: '보안과 관리자' })).toBeVisible();
  await expect(page.getByText('원본 연결 RBAC / ABAC')).toBeVisible();
  await expect(page.getByRole('row', { name: /WebDAV 저장소 1/ })).toBeVisible();
  await expect(page.getByText('webdav_src_primary')).toHaveCount(0);
  await expect(page.getByText('곧 제공됩니다')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('security-governance-desktop-access.png'), fullPage: false });

  await page.getByRole('tab', { name: '감사 로그' }).click();
  await expect(page.getByText('서버 감사 로그')).toBeVisible();
  await expect(page.getByText('보안 설정 변경이 서버 감사 근거로 기록되었습니다.')).toBeVisible();
  await expect(page.getByText('서버 관측 이벤트')).toBeVisible();
  await expect(page.getByText('audit_evt_provider_update')).toHaveCount(0);
  await expect(page.getByText('llm_provider:provider_primary')).toHaveCount(0);
  await expect(page.getByText('connector_evt_heartbeat')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('security-governance-desktop-audit.png'), fullPage: false });

  await page.getByRole('tab', { name: '외부 공유' }).click();
  await expect(page.getByText('WebDAV 저장소 쓰기 경계')).toBeVisible();
  await expect(page.getByText('외부 쓰기 실행 안 함').first()).toBeVisible();
  await page.getByRole('tab', { name: '정책' }).click();
  await expect(page.getByText('차단 우선 정책 순서')).toBeVisible();
  await expect(page.getByText('교차 조직 제공자 secret')).toBeVisible();
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('security-governance-desktop-policy.png'), fullPage: false });

  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto('/security');
  await expect(page.getByText('원본 연결 RBAC / ABAC')).toBeVisible();
  await page.getByRole('tab', { name: '정책' }).click();
  await expect(page.getByText('ABAC 차단 후 RBAC 허용')).toBeVisible();
  const tabletOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(tabletOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('security-governance-tablet-policy.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/security');
  await expect(page.getByText('원본 연결 RBAC / ABAC')).toBeVisible();
  const mobileWebdavSource = page.locator('article', { hasText: 'WebDAV 저장소 1' }).first();
  await mobileWebdavSource.scrollIntoViewIfNeeded();
  await expect(mobileWebdavSource).toBeVisible();
  await expect(page.getByText('webdav_src_primary')).toHaveCount(0);
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('security-governance-mobile-access.png'), fullPage: false });
  const securityScrollMetrics = await page.locator('#main-content main').evaluate((scroller) => {
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(securityScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(securityScrollMetrics.after).toBeGreaterThan(securityScrollMetrics.before);
  await page.screenshot({ path: testInfo.outputPath('security-governance-mobile-scroll.png'), fullPage: false });

  await page.goto('/');
  const mobileMenuButton = page.getByRole('button', { name: '워크스페이스 메뉴 열기' }).first();
  await expect(mobileMenuButton).toBeVisible();
  await mobileMenuButton.click();
  const menu = page.locator('#mobile-workspace-menu');
  await expect(menu.getByRole('link', { name: '보안', exact: true })).toHaveAttribute('href', '/security');
  await menu.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(menu.getByRole('link', { name: '설정', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('security-governance-mobile-hamburger.png'), fullPage: false });
});

test('renders Data quality surface across viewports with signed API headers', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-data.quality-e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  await page.setViewportSize({ width: 1280, height: 1024 });
  const dataRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/data/quality-surface' && request.method() === 'GET';
  });
  await page.goto('/data');
  const dataHeaders = (await dataRequest).headers();
  expectBrowserCookieSession(dataHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(dataHeaders[headerName]).toBeUndefined();
  }

  await expect(page.getByRole('heading', { name: '데이터와 파일' })).toBeVisible();
  await expect(page.getByText('감사 근거 기록됨')).toBeVisible();
  await expect(page.getByText(/준비 중/)).toHaveCount(0);
  await expect(page.getByText('최근 파일/첨부 자산')).toBeVisible();
  const assetList = page.getByLabel('문서 저장소 파일 자산');
  await expect(assetList.getByRole('button', { name: /roadmap\.md/ })).toBeVisible();
  await expect(assetList.getByRole('button', { name: /roadmap\.pdf/ })).toBeVisible();
  const assetDetail = page.getByLabel('선택한 파일 자산 상세');
  await expect(assetDetail.getByRole('heading', { name: 'roadmap.md' })).toBeVisible();
  await expect(assetDetail.getByText('워크스페이스 문서 근거')).toBeVisible();
  await expect(assetDetail.getByText('document status: uploaded')).toBeVisible();
  await expect(assetDetail.getByText('asset_repository_ready')).toHaveCount(0);
  await expect(assetDetail.getByText('doc_repository_ready')).toHaveCount(0);
  await expect(assetDetail.getByText('thread_repository_ready')).toHaveCount(0);
  await assetList.getByRole('button', { name: /blank-notes\.md/ }).click();
  await expect(assetDetail.getByRole('heading', { name: 'blank-notes.md' })).toBeVisible();
  await expect(assetDetail.getByText('본문 추출 대기')).toBeVisible();
  await expect(assetDetail.getByText('thread_missing')).toHaveCount(0);
  await expect(assetDetail.getByText('content extraction pending, canonical thread pending')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('data-quality-desktop-repository-assets.png'), fullPage: false });
  await expect(page.getByText('outbound connector heartbeat received')).toBeVisible();
  await expect(page.getByText('connector_evt_data_quality')).toHaveCount(0);
  await page.getByRole('tab', { name: '수집 파이프라인' }).click();
  await expect(page.getByText('4 emails and 3 attachments')).toBeVisible();
  await expect(page.getByText('원본 근거 연결됨').first()).toBeVisible();
  await expect(page.getByText(/준비 중/)).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('data-quality-desktop-pipeline.png'), fullPage: false });

  await page.getByRole('tab', { name: '임베딩' }).click();
  await expect(page.getByText('text-embedding-3-small').first()).toBeVisible();
  await expect(page.getByText('Email vectors')).toBeVisible();
  await expect(page.getByText('1,536').first()).toBeVisible();
  await expect(page.getByText(/준비 중/)).toHaveCount(0);
  await expect(page.getByText('28,401')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('data-quality-desktop-embedding.png'), fullPage: false });

  await page.getByRole('tab', { name: '품질 점검' }).click();
  await expect(page.getByText('Thread id integrity').first()).toBeVisible();
  await expect(page.getByText('Some scoped emails need canonical thread ids.')).toBeVisible();
  await expect(page.getByText('23건')).toHaveCount(0);
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('data-quality-desktop-quality.png'), fullPage: false });

  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto('/data');
  await expect(page.getByText('감사 근거 기록됨')).toBeVisible();
  await expect(page.getByText('data.quality_surface.viewed')).toHaveCount(0);
  await expect(page.getByText(/준비 중/)).toHaveCount(0);
  await page.getByRole('tab', { name: '수집 파이프라인' }).click();
  await expect(page.getByText('Connector observability')).toBeVisible();
  const tabletOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(tabletOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('data-quality-tablet-pipeline.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/data');
  await expect(page.getByText('감사 근거 기록됨')).toBeVisible();
  await expect(page.getByText('data.quality_surface.viewed')).toHaveCount(0);
  await page.getByRole('tab', { name: '품질 점검' }).click();
  const mobileQualityCard = page.locator('article', { hasText: 'Dedupe fingerprint' }).first();
  await mobileQualityCard.scrollIntoViewIfNeeded();
  await expect(mobileQualityCard).toBeVisible();
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('data-quality-mobile-quality.png'), fullPage: false });
  const dataScrollMetrics = await page.locator('#main-content main').evaluate((scroller) => {
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(dataScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(dataScrollMetrics.after).toBeGreaterThan(dataScrollMetrics.before);
  await page.screenshot({ path: testInfo.outputPath('data-quality-mobile-scroll.png'), fullPage: false });

  await page.goto('/');
  await page.getByRole('button', { name: '워크스페이스 메뉴 열기' }).click();
  const menu = page.locator('#mobile-workspace-menu');
  await expect(menu.getByRole('link', { name: '데이터', exact: true })).toHaveAttribute('href', '/data');
  await menu.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(menu.getByRole('link', { name: '설정', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('data-quality-mobile-hamburger.png'), fullPage: false });
});

test('renders sent mail reply tracking route with signed API headers', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-sent.mail-e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  const sentRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/emails' && url.searchParams.get('folder') === 'sent' && request.method() === 'GET';
  });

  await page.goto('/mail?folder=sent');
  const requestHeaders = (await sentRequest).headers();
  expectBrowserCookieSession(requestHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(requestHeaders[headerName]).toBeUndefined();
  }

  await expect(page.getByRole('heading', { name: '보낸 메일' }).first()).toBeVisible();
  await expect(page.getByText('답변 대기').first()).toBeVisible();
  await expect(page.getByText('응답 대기 중').first()).toBeVisible();
  await expect(page.getByText('지식 정리').first()).toBeVisible();
  await expect(page.getByText('벤더 계약 답변 요청').first()).toBeVisible();
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('sent-mail-reply-tracking-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/mail?folder=sent');
  await expect(page.getByRole('heading', { name: '보낸 메일' }).first()).toBeVisible();
  await expect(page.getByText('응답 대기 중').first()).toBeVisible();
  await expect(page.getByText('나에게 보낸 지식 메모').first()).toBeVisible();
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('sent-mail-reply-tracking-mobile.png'), fullPage: false });
  const sentScrollMetrics = await page.locator('#mobile-inbox [data-slot="scroll-area-viewport"]').evaluate((scroller) => {
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(sentScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(sentScrollMetrics.after).toBeGreaterThan(sentScrollMetrics.before);
  await page.screenshot({ path: testInfo.outputPath('sent-mail-reply-tracking-mobile-scroll.png'), fullPage: false });
});

test('updates source-linked task ticket status with signed API headers', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-task.status-e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  const patchRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/tasks/task-q2-owner' && request.method() === 'PATCH';
  });

  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: '실행 항목 추적' })).toBeVisible();
  await expect(page.getByRole('region', { name: '원본 연결 티켓 상태 보드' })).toBeVisible();
  await page.getByRole('button', { name: '리소스 배정 검토 회의 상태를 완료로 변경' }).click();
  const requestHeaders = (await patchRequest).headers();
  expectBrowserCookieSession(requestHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(requestHeaders[headerName]).toBeUndefined();
  }

  await expect(page.getByText('리소스 배정 검토 회의 상태를 완료로 변경했습니다.')).toBeVisible();
  await expect(page.getByRole('button', { name: '리소스 배정 검토 회의 상태를 완료로 변경' })).toHaveAttribute('aria-pressed', 'true');
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('task-ticket-status-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: '실행 항목 추적' })).toBeVisible();
  await expect(page.getByRole('region', { name: '원본 연결 티켓 상태 보드' })).toBeVisible();
  await expect(page.getByText('실제 티켓 큐')).toBeVisible();
  await expect(page.getByText('5개 티켓 연결')).toBeVisible();
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('task-ticket-status-mobile.png'), fullPage: false });
  const taskScrollMetrics = await page.locator('main').nth(1).evaluate((scroller) => {
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(taskScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(taskScrollMetrics.after).toBeGreaterThan(taskScrollMetrics.before);
  await page.screenshot({ path: testInfo.outputPath('task-ticket-status-mobile-scroll.png'), fullPage: false });
});

test('creates overdue reply follow-up tasks with signed API headers', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-reply.sla-e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  const desktopEscalationRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/tasks/reply-sla-escalations' && request.method() === 'POST';
  });

  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: '실행 항목 추적' })).toBeVisible();
  await page.getByRole('button', { name: '보낸 메일 미답변 팔로업 작업 생성' }).click();
  const desktopRequest = await desktopEscalationRequest;
  const desktopHeaders = desktopRequest.headers();
  expectBrowserCookieSession(desktopHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(desktopHeaders[headerName]).toBeUndefined();
  }
  expect(desktopRequest.postDataJSON()).toEqual({ overdue_hours: 48 });

  await expect(page.getByText('1개 미답변 팔로업 작업을 생성했습니다. 2개 대기 메일을 48시간 기준으로 확인했습니다.')).toBeVisible();
  const desktopTicketList = page.getByLabel('원본 연결 티켓 목록');
  await expect(desktopTicketList.getByRole('heading', { name: '미답변 팔로업: 벤더 계약 답변 요청' })).toBeVisible();
  const escalatedDesktopTask = desktopTicketList.getByRole('article').filter({ hasText: '미답변 팔로업: 벤더 계약 답변 요청' });
  await expect(escalatedDesktopTask.getByText('차단 · 긴급')).toBeVisible();
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('reply-sla-escalation-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileEscalationRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/tasks/reply-sla-escalations' && request.method() === 'POST';
  });
  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: '실행 항목 추적' })).toBeVisible();
  await page.getByRole('button', { name: '보낸 메일 미답변 팔로업 작업 생성' }).click();
  const mobileRequestHeaders = (await mobileEscalationRequest).headers();
  expectBrowserCookieSession(mobileRequestHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(mobileRequestHeaders[headerName]).toBeUndefined();
  }
  const mobileTicketList = page.getByLabel('원본 연결 티켓 목록');
  await expect(mobileTicketList.getByRole('heading', { name: '미답변 팔로업: 벤더 계약 답변 요청' })).toBeVisible();
  await mobileTicketList.getByRole('heading', { name: '미답변 팔로업: 벤더 계약 답변 요청' }).scrollIntoViewIfNeeded();
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('reply-sla-escalation-mobile.png'), fullPage: false });
  const taskScrollMetrics = await page.locator('main').nth(1).evaluate((scroller) => {
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(taskScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(taskScrollMetrics.after).toBeGreaterThan(taskScrollMetrics.before);
  await page.screenshot({ path: testInfo.outputPath('reply-sla-escalation-mobile-scroll.png'), fullPage: false });
});

test('creates self-sent knowledge WebDAV intent with signed API headers', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-self-sent.knowledge-e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  const desktopIntentRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/webdav/knowledge-materialization-intent' && request.method() === 'POST';
  });

  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: '실행 항목 추적' })).toBeVisible();
  await expect(page.getByRole('region', { name: '나에게 보낸 지식 메일 WebDAV 의도' })).toBeVisible();
  await page.getByRole('button', { name: '나에게 보낸 지식 메모 정리 WebDAV 지식 노트 의도 생성' }).click();
  const request = await desktopIntentRequest;
  const requestHeaders = request.headers();
  expectBrowserCookieSession(requestHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(requestHeaders[headerName]).toBeUndefined();
  }
  expect(request.postDataJSON()).toEqual({ source_task_id: 'task-self-knowledge' });

  await expect(page.getByText('WebDAV/Notes 의도 준비')).toBeVisible();
  await expect(page.getByText('의도만 기록')).toBeVisible();
  await expect(page.getByText('provider_write_executed=false')).toHaveCount(0);
  await expect(page.getByText('기록됨')).toBeVisible();
  await expect(page.getByText('webdav.self_sent_knowledge_intent.created')).toHaveCount(0);
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('self-sent-knowledge-webdav-intent-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileIntentRequest = page.waitForRequest((mobileRequest) => {
    const url = new URL(mobileRequest.url());
    return url.pathname === '/api/webdav/knowledge-materialization-intent' && mobileRequest.method() === 'POST';
  });
  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: '실행 항목 추적' })).toBeVisible();
  await page.getByRole('button', { name: '나에게 보낸 지식 메모 정리 WebDAV 지식 노트 의도 생성' }).click();
  const mobileRequest = await mobileIntentRequest;
  expectBrowserCookieSession(mobileRequest.headers(), expectedNaruonToken);
  await expect(page.getByText('WebDAV/Notes 의도 준비')).toBeVisible();
  await page.getByText('WebDAV/Notes 의도 준비').scrollIntoViewIfNeeded();
  await expect(page.getByText('webdav.self_sent_knowledge_intent.created')).toHaveCount(0);
  await page.locator('main').nth(1).evaluate((scroller) => {
    scroller.scrollTop += 96;
  });
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('self-sent-knowledge-webdav-intent-mobile.png'), fullPage: false });
  const taskScrollMetrics = await page.locator('main').nth(1).evaluate((scroller) => {
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(taskScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(taskScrollMetrics.after).toBeGreaterThan(taskScrollMetrics.before);
  await page.screenshot({ path: testInfo.outputPath('self-sent-knowledge-webdav-intent-mobile-scroll.png'), fullPage: false });
});

test('renders the settings self-hosted connector manifest with mobile scrolling', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDashboardApi(page);

  await page.goto('/settings');
  await page.getByRole('button', { name: '개발자' }).first().click();

  await expect(page.getByRole('region', { name: 'Self-hosted connector manifest' })).toBeVisible();
  await expect(page.getByText('Self-hosted connector 등록 상태')).toBeVisible();
  await expect(page.getByText('Naruon은 메일 서버가 아닙니다')).toBeVisible();
  await expect(page.getByText('naruon.net')).toBeVisible();
  await expect(page.getByText('검증용 연결')).toBeVisible();
  await expect(page.getByText('SMTP 서버 역할 금지')).toBeVisible();
  await expect(page.getByText('Connector 상태와 APM 신호')).toBeVisible();
  await expect(page.getByText('감사 근거 기록됨')).toBeVisible();
  await expect(page.getByText('OTel endpoint')).toBeVisible();
  await expect(page.getByText('최근 connector 신호')).toBeVisible();
  await expect(page.getByText('서버가 runner 하트비트를 관측했습니다.')).toBeVisible();
  await expect(page.getByText('계측 준비')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('settings-connector-apm-mobile.png'), fullPage: false });
  await page.getByText('최근 connector 신호').scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('settings-connector-apm-mobile-history.png'), fullPage: false });

  const scrollMetrics = await page.evaluate(() => {
    const scroller = Array.from(document.querySelectorAll('body, body *')).find((element) => {
      const style = window.getComputedStyle(element);
      return style.overflowY !== 'hidden' && element.scrollHeight > element.clientHeight + 10;
    });
    if (!scroller) return null;
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(scrollMetrics).not.toBeNull();
  expect(scrollMetrics?.maxScroll).toBeGreaterThan(0);
  expect(scrollMetrics?.after).toBeGreaterThan(scrollMetrics?.before ?? 0);
  await page.screenshot({ path: testInfo.outputPath('settings-connector-apm-mobile-scroll.png'), fullPage: false });
});

test('renders settings connector APM signals across desktop and tablet', async ({ page }, testInfo) => {
  await mockDashboardApi(page);

  for (const viewport of [
    { name: 'desktop', width: 1280, height: 1024 },
    { name: 'tablet', width: 1024, height: 768 },
  ] as const) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/settings');
    await page.getByRole('button', { name: '개발자' }).first().click();

    await expect(page.getByText('Connector 상태와 APM 신호')).toBeVisible();
    await expect(page.getByText('감사 근거 기록됨')).toBeVisible();
    await expect(page.getByText('OTel endpoint')).toBeVisible();
    await expect(page.getByText('최근 connector 신호')).toBeVisible();
    await expect(page.getByText('Connector heartbeat')).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.getByText('서버가 runner 하트비트를 관측했습니다.').scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`settings-connector-apm-${viewport.name}.png`), fullPage: false });
  }
});

test('renders source-backed mail account settings across desktop tablet and mobile', async ({ page }, testInfo) => {
  const accountRequests: {
    method: string;
    headers: Record<string, string>;
    postData: string | null;
  }[] = [];

  await page.addInitScript(() => {
    document.cookie = 'naruon_session=signed-settings.e2e.token; Path=/; SameSite=Lax';
  });
  await mockDashboardApi(page, (path, request) => {
    if (path === '/api/accounts/config') {
      accountRequests.push({
        method: request.method(),
        headers: request.headers(),
        postData: request.postData(),
      });
    }
  });

  for (const viewport of [
    { name: 'desktop', width: 1280, height: 1024 },
    { name: 'tablet', width: 1024, height: 768 },
    { name: 'mobile', width: 390, height: 844 },
  ] as const) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/settings');
    await page.getByRole('button', { name: '연결 계정' }).first().click();

    await expect(page.getByText('고객 지정 연결')).toBeVisible();
    await expect(page.getByText('Naruon은 메일함 용량이나 SMTP/IMAP 서버를 제공하지 않습니다')).toBeVisible();
    await expect(page.getByText('smtp.example.com:587')).toBeVisible();
    await expect(page.getByText('imap.example.com:993')).toBeVisible();
    await expect(page.getByText('pop3.example.com:995')).toBeVisible();
    await expect(page.getByText('OAuth 로그인')).toBeVisible();
    await expect(page.getByText('원본 연결 준비 상태')).toBeVisible();
    await expect(page.getByText('Customer CalDAV 일정 원본 1')).toBeVisible();
    await expect(page.getByLabel('연동 원본 준비도').getByText('WebDAV 저장소 1', { exact: true })).toBeVisible();
    await expect(page.getByText('webdav_src_primary')).toHaveCount(0);
    await expect(page.getByText('저장된 secret 유지').first()).toBeVisible();

    if (viewport.name === 'desktop') {
      await page.getByRole('button', { name: '계정 설정 저장' }).click();
      await expect(page.getByText('계정 설정을 저장했습니다')).toBeVisible();
    }

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: testInfo.outputPath(`settings-mail-account-${viewport.name}.png`), fullPage: false });
  }

  await page.setViewportSize({ width: 390, height: 640 });
  await page.goto('/settings');
  await page.getByRole('button', { name: '연결 계정' }).first().click();
  await page.getByLabel('OAuth redirect URI').scrollIntoViewIfNeeded();
  const mobileScrollMetrics = await page.evaluate(() => {
    const scroller = Array.from(document.querySelectorAll('main, main *')).find((element) => {
      const style = window.getComputedStyle(element);
      return style.overflowY !== 'hidden' && element.scrollHeight > element.clientHeight + 10;
    });
    if (!scroller) return null;
    scroller.scrollTop = 0;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(mobileScrollMetrics).not.toBeNull();
  expect(mobileScrollMetrics?.maxScroll).toBeGreaterThan(0);
  expect(mobileScrollMetrics?.after).toBeGreaterThan(mobileScrollMetrics?.before ?? 0);
  await page.screenshot({ path: testInfo.outputPath('settings-mail-account-mobile-scroll.png'), fullPage: false });

  const getRequest = accountRequests.find((request) => request.method === 'GET');
  expectBrowserCookieSession(getRequest?.headers, 'signed-settings.e2e.token');
  for (const header of ['x-user-id', 'x-organization-id', 'x-group-id', 'x-group-ids', 'x-user-role', 'x-dev-auth-token']) {
    expect(getRequest?.headers[header]).toBeUndefined();
  }

  const putRequest = accountRequests.find((request) => request.method === 'PUT');
  expectBrowserCookieSession(putRequest?.headers, 'signed-settings.e2e.token');
  const putBody = JSON.parse(putRequest?.postData || '{}') as Record<string, unknown>;
  expect(putBody).toMatchObject({
    smtp_server: 'smtp.example.com',
    smtp_port: 587,
    smtp_username: 'sender@example.com',
    imap_server: 'imap.example.com',
    imap_port: 993,
    imap_username: 'inbox@example.com',
    pop3_server: 'pop3.example.com',
    pop3_port: 995,
    pop3_username: 'archive@example.com',
    oauth_client_id: 'oauth-client-id',
    oauth_redirect_uri: 'https://naruon.net/oauth/mail/callback',
  });
  expect(putBody).not.toHaveProperty('smtp_password');
  expect(putBody).not.toHaveProperty('imap_password');
  expect(putBody).not.toHaveProperty('pop3_password');
  expect(putBody).not.toHaveProperty('oauth_client_secret');
});

test('renders calendar writeback intent status without direct provider writes', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-calendar.e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  await page.goto('/calendar');
  await expect(page.getByText('일정 원본 1').first()).toBeVisible();
  await expect(page.getByText('CalDAV 원본').first()).toBeVisible();
  await expect(page.getByText('충돌 토큰 있음')).toBeVisible();
  await expect(page.getByText('etag=etag-caldav-primary')).toHaveCount(0);
  const desktopWritebackRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/calendar/writeback-intent' && request.method() === 'POST';
  });
  await page.getByRole('button', { name: '새 일정 intent 점검' }).click();
  const desktopWritebackCall = await desktopWritebackRequest;
  const desktopRequestHeaders = desktopWritebackCall.headers();
  expectBrowserCookieSession(desktopRequestHeaders, expectedNaruonToken);
  expect(desktopWritebackCall.postDataJSON()).toEqual({
    action: 'create',
    summary: 'Naruon 일정 후보 writeback intent 점검',
    target_source_id: 'caldav-primary',
  });
  for (const headerName of publicIdentityHeaders) {
    expect(desktopRequestHeaders[headerName]).toBeUndefined();
  }

  await expect(page.getByText('고객 원본 계정 반영')).toBeVisible();
  await expect(page.getByText('CalDAV 원본 선택됨')).toBeVisible();
  await expect(page.getByRole('status').getByText('선택한 일정 원본')).toBeVisible();
  await expect(page.getByRole('status').getByText('기록됨')).toBeVisible();
  await expect(page.getByText('calendar.writeback_intent.created')).toHaveCount(0);
  await expect(page.getByText('caldav-primary')).toHaveCount(0);
  await expect(page.getByText('동기화 완료')).toHaveCount(0);
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('calendar-writeback-intent-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/calendar');
  await expect(page.getByRole('heading', { name: '일정 관리' })).toBeVisible();
  await expect(page.getByText('일정 원본 1').first()).toBeVisible();
  const mobileWritebackRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/calendar/writeback-intent' && request.method() === 'POST';
  });
  await page.getByRole('button', { name: '새 일정 intent 점검' }).click();
  const mobileWritebackCall = await mobileWritebackRequest;
  const mobileRequestHeaders = mobileWritebackCall.headers();
  expectBrowserCookieSession(mobileRequestHeaders, expectedNaruonToken);
  expect(mobileWritebackCall.postDataJSON()).toEqual({
    action: 'create',
    summary: 'Naruon 일정 후보 writeback intent 점검',
    target_source_id: 'caldav-primary',
  });
  for (const headerName of publicIdentityHeaders) {
    expect(mobileRequestHeaders[headerName]).toBeUndefined();
  }
  await expect(page.getByText('고객 원본 계정 반영')).toBeVisible();
  await expect(page.getByText('caldav-primary')).toHaveCount(0);
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('calendar-writeback-intent-mobile.png'), fullPage: false });
  const calendarScrollMetrics = await page.evaluate(() => {
    const scroller = Array.from(document.querySelectorAll('main div')).find((element) => {
      const style = window.getComputedStyle(element);
      return style.overflowY !== 'hidden' && element.scrollHeight > element.clientHeight + 10;
    });
    if (!scroller) return null;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(calendarScrollMetrics).not.toBeNull();
  expect(calendarScrollMetrics?.maxScroll).toBeGreaterThan(0);
  expect(calendarScrollMetrics?.after).toBeGreaterThan(calendarScrollMetrics?.before ?? 0);
  await page.screenshot({ path: testInfo.outputPath('calendar-writeback-intent-mobile-scroll.png'), fullPage: false });
});

test('renders data WebDAV writeback intent and document materialization status', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-webdav.e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  const desktopAccountsRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/webdav/accounts' && request.method() === 'GET';
  }, { timeout: 60_000 });
  await page.goto('/data');
  const desktopAccountsCall = await desktopAccountsRequest;
  const desktopAccountsHeaders = desktopAccountsCall.headers();
  expectBrowserCookieSession(desktopAccountsHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(desktopAccountsHeaders[headerName]).toBeUndefined();
  }
  await expect(page.getByText('쓰기 가능 · 충돌 검사용 ETag 준비')).toBeVisible();
  const desktopWritebackRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/webdav/writeback-intent' && request.method() === 'POST';
  }, { timeout: 60_000 });
  await page.getByRole('button', { name: 'WebDAV 반영 의도 점검' }).click();
  const desktopWritebackCall = await desktopWritebackRequest;
  const desktopHeaders = desktopWritebackCall.headers();
  expectBrowserCookieSession(desktopHeaders, expectedNaruonToken);
  expect(desktopWritebackCall.postDataJSON()).toEqual({ target_source_id: 'webdav_src_primary' });
  for (const headerName of publicIdentityHeaders) {
    expect(desktopHeaders[headerName]).toBeUndefined();
  }

  await expect(page.getByText('원본 반영 의도')).toBeVisible();
  await expect(page.getByText('서버 확인')).toBeVisible();
  await expect(page.getByText('WebDAV 저장소 1').first()).toBeVisible();
  await expect(page.getByText('WebDAV source webdav_src_primary')).toHaveCount(0);
  await expect(page.getByText('https://webdav.naruon.net')).toHaveCount(0);
  await expect(page.getByText('etag-webdav-primary')).toHaveCount(0);
  const desktopMaterializationRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return (
      url.pathname === '/api/data/documents/doc_repository_ready/webdav-materialization-intent'
      && request.method() === 'POST'
    );
  }, { timeout: 60_000 });
  await page.getByRole('button', { name: 'WebDAV 문서 실행 요청' }).click();
  const desktopMaterializationCall = await desktopMaterializationRequest;
  const desktopMaterializationHeaders = desktopMaterializationCall.headers();
  expectBrowserCookieSession(desktopMaterializationHeaders, expectedNaruonToken);
  expect(desktopMaterializationCall.postDataJSON()).toEqual({
    target_source_id: 'webdav_src_primary',
    execute_provider: true,
  });
  for (const headerName of publicIdentityHeaders) {
    expect(desktopMaterializationHeaders[headerName]).toBeUndefined();
  }
  await expect(page.getByText('외부 쓰기 실행됨')).toBeVisible();
  await expect(page.getByText('Workspace document WebDAV materialization executed')).toBeVisible();
  await expect(page.getByText('/Naruon/Data/roadmap.md-opaque.md')).toHaveCount(0);
  await expect(page.getByText('runner_req_data_doc_1')).toHaveCount(0);
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('data-webdav-writeback-intent-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/data');
  await expect(page.getByRole('heading', { name: '데이터와 파일' })).toBeVisible();
  const mobileWritebackRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/webdav/writeback-intent' && request.method() === 'POST';
  }, { timeout: 60_000 });
  await page.getByRole('button', { name: 'WebDAV 반영 의도 점검' }).click();
  const mobileWritebackCall = await mobileWritebackRequest;
  const mobileHeaders = mobileWritebackCall.headers();
  expectBrowserCookieSession(mobileHeaders, expectedNaruonToken);
  expect(mobileWritebackCall.postDataJSON()).toEqual({ target_source_id: 'webdav_src_primary' });
  for (const headerName of publicIdentityHeaders) {
    expect(mobileHeaders[headerName]).toBeUndefined();
  }
  await expect(page.getByText('서버 확인')).toBeVisible();
  await page.getByText('서버 확인').scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 140);
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('data-webdav-writeback-intent-mobile.png'), fullPage: false });
  const dataScrollMetrics = await page.evaluate(() => {
    const scroller = Array.from(document.querySelectorAll('main, main *')).find((element) => {
      const style = window.getComputedStyle(element);
      return style.overflowY !== 'hidden' && element.scrollHeight > element.clientHeight + 10;
    });
    if (!scroller) return null;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(dataScrollMetrics).not.toBeNull();
  expect(dataScrollMetrics?.maxScroll).toBeGreaterThan(0);
  expect(dataScrollMetrics?.after).toBeGreaterThan(dataScrollMetrics?.before ?? 0);
  await page.screenshot({ path: testInfo.outputPath('data-webdav-writeback-intent-mobile-scroll.png'), fullPage: false });
});

test('renders unique email canonical thread intent with signed API headers', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-email.dedupe-e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  await page.goto('/data');
  const desktopIntentRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/emails/unique-thread-intent' && request.method() === 'POST';
  });
  await page.getByRole('button', { name: '중복 메일 스레드 의도 점검' }).click();
  const desktopRequest = await desktopIntentRequest;
  const desktopHeaders = desktopRequest.headers();
  expectBrowserCookieSession(desktopHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(desktopHeaders[headerName]).toBeUndefined();
  }
  expect(desktopRequest.postDataJSON().candidates).toHaveLength(2);
  const desktopUniqueThreadSection = page.getByLabel('중복 메일 canonical 스레드 의도');
  await expect(desktopUniqueThreadSection.getByText('기록됨')).toBeVisible();
  await expect(desktopUniqueThreadSection.getByText('의도만 기록')).toBeVisible();
  await expect(page.getByText('email.unique_thread_intent.created')).toHaveCount(0);
  await expect(page.getByText('provider_write_executed=false')).toHaveCount(0);
  await expect(page.getByText('본문 fingerprint 근거')).toBeVisible();
  await expect(page.getByText('thread-q2-root')).toHaveCount(0);
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('data-unique-thread-intent-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/data');
  await expect(page.getByRole('heading', { name: '데이터와 파일' })).toBeVisible();
  const mobileIntentRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/emails/unique-thread-intent' && request.method() === 'POST';
  });
  await page.getByRole('button', { name: '중복 메일 스레드 의도 점검' }).click();
  const mobileHeaders = (await mobileIntentRequest).headers();
  expectBrowserCookieSession(mobileHeaders, expectedNaruonToken);
  for (const headerName of publicIdentityHeaders) {
    expect(mobileHeaders[headerName]).toBeUndefined();
  }
  const mobileUniqueThreadSection = page.getByLabel('중복 메일 canonical 스레드 의도');
  await expect(mobileUniqueThreadSection.getByText('본문 fingerprint 근거')).toBeVisible();
  await expect(page.getByText('thread-q2-root')).toHaveCount(0);
  await mobileUniqueThreadSection.getByText('기록됨').scrollIntoViewIfNeeded();
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('data-unique-thread-intent-mobile.png'), fullPage: false });
  const dataScrollMetrics = await page.evaluate(() => {
    const scroller = Array.from(document.querySelectorAll('main, main *')).find((element) => {
      const style = window.getComputedStyle(element);
      return style.overflowY !== 'hidden' && element.scrollHeight > element.clientHeight + 10;
    });
    if (!scroller) return null;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(dataScrollMetrics).not.toBeNull();
  expect(dataScrollMetrics?.maxScroll).toBeGreaterThan(0);
  expect(dataScrollMetrics?.after).toBeGreaterThan(dataScrollMetrics?.before ?? 0);
  await page.screenshot({ path: testInfo.outputPath('data-unique-thread-intent-mobile-scroll.png'), fullPage: false });
});

test('renders API-backed context search sender DAG and reply tracking', async ({ page }, testInfo) => {
  const expectedNaruonToken = 'signed-search.e2e.token';
  const publicIdentityHeaders = [
    'x-user-id',
    'x-organization-id',
    'x-group-id',
    'x-group-ids',
    'x-user-role',
    'x-dev-auth-token',
  ];
  await page.setViewportSize({ width: 1280, height: 1024 });
  await mockDashboardApi(page);
  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, expectedNaruonToken);

  const searchRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/search' && request.method() === 'POST';
  });
  const graphRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/network/graph' && request.method() === 'GET';
  });
  const ontologyRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === '/api/ontology/relationships' && request.method() === 'GET';
  });

  await page.goto('/search');
  const searchHeaders = (await searchRequest).headers();
  const graphHeaders = (await graphRequest).headers();
  const ontologyCall = await ontologyRequest;
  const ontologyHeaders = ontologyCall.headers();
  expectBrowserCookieSession(searchHeaders, expectedNaruonToken);
  expectBrowserCookieSession(graphHeaders, expectedNaruonToken);
  expectBrowserCookieSession(ontologyHeaders, expectedNaruonToken);
  const ontologyUrl = new URL(ontologyCall.url());
  expect(ontologyUrl.searchParams.get('source_message_id')).toBe('<q2@example.com>');
  expect(ontologyUrl.searchParams.get('source_thread_id')).toBe('thread-q2');
  for (const headerName of publicIdentityHeaders) {
    expect(searchHeaders[headerName]).toBeUndefined();
    expect(graphHeaders[headerName]).toBeUndefined();
    expect(ontologyHeaders[headerName]).toBeUndefined();
  }

  await expect(page.getByRole('heading', { name: '맥락 검색' })).toBeAttached();
  await expect(page.getByRole('heading', { name: 'Q2 출시 계획 및 우선순위 조정' }).first()).toBeVisible();
  await expect(page.getByText('thread-q2').first()).toBeVisible();
  await expect(page.getByText('답장 2건').first()).toBeVisible();
  await expect(page.getByText('관계 맥락과 타임라인')).toBeVisible();
  await expect(page.getByText('발신자 DAG (Ontology)')).toBeVisible();
  await expect(page.getByText('track_reply_and_tasks')).toBeVisible();
  await expect(page.getByText('source=<q2@example.com> / thread=thread-q2')).toBeVisible();
  await expect(page.getByText('김지현 PM').first()).toBeVisible();
  const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('search-dag-reply-desktop.png'), fullPage: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/search');
  await expect(page.getByRole('heading', { name: 'Q2 출시 계획 및 우선순위 조정' }).first()).toBeVisible();
  await expect(page.getByText('thread-q2').first()).toBeVisible();
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('search-dag-reply-mobile.png'), fullPage: false });
  const resultScrollMetrics = await page.locator('aside').evaluate((scroller) => {
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(resultScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(resultScrollMetrics.after).toBeGreaterThan(resultScrollMetrics.before);

  const detailScrollMetrics = await page.locator('main main').evaluate((scroller) => {
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    return {
      before,
      after: scroller.scrollTop,
      maxScroll: scroller.scrollHeight - scroller.clientHeight,
    };
  });
  expect(detailScrollMetrics.maxScroll).toBeGreaterThan(0);
  expect(detailScrollMetrics.after).toBeGreaterThan(detailScrollMetrics.before);
  await page.getByText('발신자 DAG (Ontology)').scrollIntoViewIfNeeded();
  await expect(page.getByText('track_reply_and_tasks')).toBeVisible();
  await page.getByText('track_reply_and_tasks').scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('search-dag-reply-mobile-dag.png'), fullPage: false });
  await page.getByText('관계 이해').scrollIntoViewIfNeeded();
  await expect(page.getByText('관계 이해')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('search-dag-reply-mobile-scroll.png'), fullPage: false });
});

test('captures responsive startup evidence for desktop tablet mobile and the mobile drawer', async ({ page }, testInfo) => {
  await mockDashboardApi(page);
  for (const viewport of [
    { name: 'desktop', width: 1280, height: 1024 },
    { name: 'tablet', width: 1024, height: 768 },
    { name: 'mobile', width: 390, height: 844 },
  ] as const) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto('/');
    await expect(page.getByRole('region', { name: '홈 개요' }).first()).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`startup-${viewport.name}.png`), fullPage: true });
    if (viewport.name === 'mobile') {
      await page.getByRole('button', { name: '워크스페이스 메뉴 열기' }).click();
      await expect(page.getByRole('dialog', { name: '모바일 워크스페이스 메뉴' })).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath('startup-mobile-drawer.png'), fullPage: true });
    }
  }
});

test('validates mobile hamburger composition and startup preference controls', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDashboardApi(page);

  await page.goto('/');
  await page.getByRole('button', { name: '워크스페이스 메뉴 열기' }).click();

  const menu = page.locator('#mobile-workspace-menu');
  const menuWidth = await menu.evaluate((element) => element.getBoundingClientRect().width);
  expect(menuWidth).toBeGreaterThanOrEqual(340);
  await expect(menu.getByText('시작 화면', { exact: true })).toBeVisible();
  await expect(menu.getByRole('button', { name: '홈' })).toBeVisible();
  await expect(menu.getByRole('button', { name: '메일' })).toBeVisible();
  await expect(menu.getByRole('button', { name: '일정' })).toBeVisible();
  await expect(menu.getByRole('link', { name: '홈', exact: true })).toHaveAttribute('href', '/');
  await expect(menu.getByRole('link', { name: '메일', exact: true })).toHaveAttribute('href', '/mail');
  await expect(menu.getByRole('link', { name: /보낸 메일/ })).toHaveAttribute('href', '/mail?folder=sent');
  await expect(menu.getByRole('link', { name: '일정', exact: true })).toHaveAttribute('href', '/calendar');
  await expect(menu.getByRole('link', { name: '맥락 검색', exact: true })).toHaveAttribute('href', '/search');
  await expect(menu.getByRole('link', { name: 'AI 허브', exact: true })).toHaveAttribute('href', '/ai-hub');
  await expect(menu.getByText('워크스페이스', { exact: true })).toBeVisible();
  await expect(menu.getByText('주요 작업공간', { exact: true })).toBeVisible();
  await expect(menu.getByText('도움', { exact: true })).toBeVisible();
  await expect(menu.getByRole('link', { name: '작업', exact: true })).toHaveAttribute('href', '/tasks');
  await expect(menu.getByRole('link', { name: '프로젝트', exact: true })).toHaveAttribute('href', '/projects');
  await expect(menu.getByRole('link', { name: '데이터', exact: true })).toHaveAttribute('href', '/data');
  await expect(menu.getByRole('link', { name: '보안', exact: true })).toHaveAttribute('href', '/security');
  await expect(menu.getByRole('link', { name: '설정', exact: true })).toHaveAttribute('href', '/settings');
  await expect(menu.getByRole('link', { name: '도움말', exact: true })).toHaveAttribute('href', '/settings#help');
  await expect(menu.getByRole('link', { name: '프로필', exact: true })).toHaveAttribute('href', '/settings#profile');
  const desktopDestinationHrefs = await page
    .locator('nav[aria-label="Primary workspace navigation"] a')
    .evaluateAll((links) => links.map((link) => link.getAttribute('href')));
  const mobileDestinationHrefs = await menu
    .locator('nav[aria-label="Mobile primary destinations"] a')
    .evaluateAll((links) => links.map((link) => link.getAttribute('href')));
  expect(mobileDestinationHrefs).toEqual(desktopDestinationHrefs);
  await expect(menu.getByRole('link', { name: /일정 연결/ })).toHaveAttribute('href', '#mobile-calendar');
  await expect(menu.getByText(/준비 중/)).toHaveCount(0);
  await menu.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(menu.getByText('도움말')).toBeVisible();
  await expect(menu.getByText('프로필')).toBeVisible();
  const utilityGap = await menu.getByText('프로필').evaluate((element) => {
    const item = element.getBoundingClientRect();
    const dialog = document.querySelector('#mobile-workspace-menu')?.getBoundingClientRect();
    return dialog ? dialog.bottom - item.bottom : 0;
  });
  expect(utilityGap).toBeGreaterThanOrEqual(0);
  await page.screenshot({ path: testInfo.outputPath('mobile-workspace-menu.png'), fullPage: true });

  await menu.getByRole('button', { name: '일정' }).click();
  await expect(page.getByRole('button', { name: '워크스페이스 메뉴 열기' })).toHaveAttribute('aria-expanded', 'false');
  await expect(menu.getByText('시작 화면', { exact: true })).toBeHidden();
});

for (const viewport of [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'desktop', width: 1280, height: 1024 },
] as const) {
  test(`renders the functional AI hub sections without horizontal overflow at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockDashboardApi(page);

    await page.goto('/ai-hub');

    await expect(page.getByRole('heading', { name: 'AI 허브' })).toBeVisible();
    await expect(page.getByRole('region', { name: '맥락 종합' })).toBeVisible();
    await expect(page.getByRole('region', { name: '판단 포인트' })).toBeVisible();
    await expect(page.getByRole('region', { name: '실행 항목' })).toBeVisible();
    await expect(page.getByText('최근 AI 요약')).toHaveCount(0);
    await expect(page.getByText('설명 없음')).toHaveCount(0);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

for (const section of [
  { hash: 'context', linkName: /맥락 종합/, region: '맥락 종합' },
  { hash: 'decisions', linkName: /판단 포인트/, region: '판단 포인트' },
  { hash: 'actions', linkName: /실행 항목/, region: '실행 항목' },
] as const) {
  test(`deep-links the AI hub execution checkpoint to ${section.region}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1024 });
    await mockDashboardApi(page);

    await page.goto('/ai-hub');
    await page
      .getByRole('navigation', { name: 'AI 허브 실행 체크포인트' })
      .getByRole('link', { name: section.linkName })
      .click();

    await expect(page).toHaveURL(new RegExp(`/ai-hub#${section.hash}$`));
    await expect(page.getByRole('region', { name: section.region })).toBeVisible();
    const targetTop = await page.getByRole('region', { name: section.region }).evaluate((element) => Math.round(element.getBoundingClientRect().top));
    expect(targetTop).toBeGreaterThanOrEqual(0);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

for (const panel of [
  { hash: 'mobile-inbox', region: '모바일 받은편지함', finalText: 'Q2 출시 계획 및 우선순위 조정', oldPlaceholder: '사람 결과 준비 중' },
  { hash: 'mobile-search', region: '모바일 맥락 검색', finalText: '강민수 의사결정 메모', oldPlaceholder: '사람 결과 준비 중' },
  { hash: 'mobile-calendar', region: '모바일 일정 연결', finalText: '파트너 미팅 일정 확정', oldPlaceholder: '디자인 리뷰 후속 조치' },
] as const) {
  test(`allows short mobile users to scroll the ${panel.region} panel past the bottom nav`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 640 });
    await mockDashboardApi(page);

    await page.goto(`/#${panel.hash}`);

    const region = page.getByRole('region', { name: panel.region });
    await expect(region).toBeVisible();
    await expect(region.getByText(panel.oldPlaceholder)).toHaveCount(0);
    await expect(region.getByText(panel.finalText)).toBeVisible();
    await region.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    const bottomGap = await region.getByText(panel.finalText).evaluate((element) => {
      const item = element.getBoundingClientRect();
      const nav = document.querySelector('nav[aria-label="Mobile workspace sections"]')?.getBoundingClientRect();
      return nav ? nav.top - item.bottom : 0;
    });
    expect(bottomGap).toBeGreaterThanOrEqual(0);
  });
}

test('keeps selected mobile email detail and actions above the bottom navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 640 });
  await mockDashboardApi(page);

  await page.goto('/');
  await page.getByRole('button', { name: '메일함 바로가기' }).first().click();
  await page.getByRole('button', { name: /김지현 PM/ }).click();

  const detailRegion = page.getByRole('region', { name: '모바일 메일 상세' });
  await expect(detailRegion).toBeVisible();
  await expect(detailRegion.getByText('Q2 출시 계획 및 우선순위 조정')).toBeVisible();
  await expect(detailRegion.getByText('출시 일정, 마케팅 계획, 파트너 미팅')).toBeVisible();
  await expect(detailRegion.getByRole('button', { name: '실행 항목 생성' })).toBeVisible();

  const replyButton = detailRegion.getByRole('button', { name: '답장 보내기' });
  await replyButton.scrollIntoViewIfNeeded();
  const bottomGap = await replyButton.evaluate((element) => {
    const item = element.getBoundingClientRect();
    const nav = document.querySelector('nav[aria-label="Mobile workspace sections"]')?.getBoundingClientRect();
    return nav ? nav.top - item.bottom : 0;
  });
  expect(bottomGap).toBeGreaterThanOrEqual(0);

  await page.getByRole('button', { name: 'AI 빠른 실행' }).click();
  await page.getByRole('dialog', { name: 'AI 빠른 실행 메뉴' }).getByRole('button', { name: '실행 항목 생성' }).click();
  await expect(detailRegion.getByText('2개 실행 항목을 티켓형 실행 항목으로 추적합니다.')).toBeVisible();
});
