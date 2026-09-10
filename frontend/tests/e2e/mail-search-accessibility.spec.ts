import { expect, test, type Route } from '@playwright/test';

import { mockDashboardApi } from './helpers';

const JSON_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Content-Type': 'application/json',
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

test('distinguishes empty inbox and submitted empty search in the browser accessibility tree', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Desktop mail workspace has its own labelled region.');

  await mockDashboardApi(page);
  await page.route('**/api/emails**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'GET' && url.pathname === '/api/emails' && !url.searchParams.has('folder')) {
      await fulfillJson(route, { emails: [] });
      return;
    }
    await route.fallback();
  });
  await page.route('**/api/search', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, { results: [] });
      return;
    }
    await route.fallback();
  });

  await page.goto('/');
  await page.getByRole('button', { name: '메일함 바로가기' }).first().click();

  const workspace = page.getByRole('region', { name: '데스크톱 메일 작업공간' });
  const inboxStatus = workspace.getByRole('status').filter({ hasText: '받은 메일이 없습니다' });
  await expect(inboxStatus).toBeVisible();
  await expect(inboxStatus).toContainText('메일 동기화 후 받은 스레드가 표시됩니다.');

  await workspace.getByRole('searchbox', { name: '메일 맥락 검색' }).fill('없는 검색어');
  await workspace.getByRole('button', { name: '맥락 검색' }).click();

  const searchStatus = workspace.getByRole('status').filter({ hasText: '맥락 검색 결과가 없습니다' });
  await expect(searchStatus).toBeVisible();
  await expect(searchStatus).toContainText('맥락 검색어를 바꾸거나 메일 동기화 상태를 확인하세요.');
  await expect(searchStatus.getByRole('button')).toHaveCount(0);
  await expect(searchStatus.getByRole('link')).toHaveCount(0);

  await workspace.getByRole('button', { name: '맥락 검색어 지우기' }).click();
  await expect(inboxStatus).toBeVisible();
});

test('announces an empty context-search result as a polite status', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Context-search desktop semantics are verified once per run.');

  await mockDashboardApi(page);
  await page.route('**/api/search', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, { results: [] });
      return;
    }
    await route.fallback();
  });

  await page.goto('/search');

  const emptyStatus = page.getByRole('status').filter({ hasText: '맥락 검색 결과가 없습니다.' });
  await expect(emptyStatus).toBeVisible();
  await expect(emptyStatus).toHaveAttribute('aria-live', 'polite');
});

test('keeps sender relationship actions outside the live status and exposes capture failure as an alert', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Context-search desktop semantics are verified once per run.');

  await mockDashboardApi(page);
  await page.route('**/api/ontology/relationships**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'GET' && url.pathname === '/api/ontology/relationships') {
      await fulfillJson(route, []);
      return;
    }
    if (request.method() === 'POST' && url.pathname === '/api/ontology/relationships/capture-source') {
      await fulfillJson(route, { detail: 'capture failed for browser regression' }, 500);
      return;
    }
    await route.fallback();
  });

  await page.goto('/search');
  await expect(page.getByRole('heading', { level: 2, name: 'Q2 출시 계획 및 우선순위 조정' })).toBeVisible();

  const relationshipStatus = page.getByRole('status').filter({
    hasText: '이 맥락 검색 결과에 연결된 발신자 관계가 아직 없습니다.',
  });
  await expect(relationshipStatus).toBeVisible();
  await expect(relationshipStatus).toHaveAttribute('aria-live', 'polite');
  await expect(relationshipStatus.getByRole('button')).toHaveCount(0);

  const captureButton = page.getByRole('button', { name: '발신자 관계 캡처' });
  await expect(captureButton).toBeVisible();
  await captureButton.click();

  await expect(page.getByRole('alert').filter({ hasText: '발신자 관계 캡처에 실패했습니다.' })).toBeVisible();
});
