import { expect, test } from '@playwright/test';
import crypto from 'node:crypto';

const liveSessionPayload = {
  ver: 1,
  iss: 'naruon-control-plane',
  aud: 'naruon-api',
  sub: 'testuser',
  role: 'member',
  org: 'org-acme',
  groups: ['group-1', 'group-2'],
  workspace: 'workspace-org-acme',
};

function encodeJson(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function signLiveSession(): string {
  const secret = process.env.LIVE_E2E_SESSION_SECRET;
  if (!secret) {
    throw new Error('LIVE_E2E_SESSION_SECRET is required for live smoke tests.');
  }

  const header = encodeJson({ alg: 'HS256', typ: 'JWT' });
  const payload = encodeJson({
    ...liveSessionPayload,
    exp: Math.floor(Date.now() / 1000) + 300,
  });
  const signature = crypto
    .createHmac('sha256', secret)
    .update(`${header}.${payload}`, 'ascii')
    .digest('base64url');

  return `${header}.${payload}.${signature}`;
}

async function hasVisibleSeededInboxText(page: import('@playwright/test').Page): Promise<boolean> {
  return page.getByText('Live E2E Release').evaluateAll((elements) =>
    elements.some((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.display !== 'none' &&
        style.visibility !== 'hidden' &&
        rect.width > 0 &&
        rect.height > 0
      );
    }),
  );
}

async function installLiveSession(page: import('@playwright/test').Page): Promise<string> {
  const sessionToken = signLiveSession();

  await page.addInitScript((token) => {
    document.cookie = `naruon_session=${token}; Path=/; SameSite=Lax`;
  }, sessionToken);
  return sessionToken;
}

test.skip(
  !process.env.LIVE_BASE_URL && process.env.RUN_LIVE_E2E !== '1',
  'Requires a live frontend/backend environment with seeded data.',
);

test.beforeEach(async ({ page }) => {
  page.on('console', (message) => {
    if (['warning', 'error'].includes(message.type())) {
      throw new Error(`Console ${message.type()}: ${message.text()}`);
    }
  });
  page.on('pageerror', (error) => {
    throw error;
  });
});

test('live dashboard renders seeded inbox through real HTTP', async ({ page }) => {
  await installLiveSession(page);
  await page.goto('/');

  await expect(page.getByRole('img', { name: 'Naruon' })).toBeVisible();
  await expect.poll(() => hasVisibleSeededInboxText(page), {
    timeout: 15_000,
  }).toBe(true);
  await expect(page.getByText('Failed to load emails.')).toHaveCount(0);
});

test('live data workspace reaches backend-backed WebDAV and document APIs without 503', async ({
  page,
}) => {
  await installLiveSession(page);

  const failedResponses: string[] = [];
  page.on('response', (response) => {
    const url = response.url();
    if (url.includes('/api/') && response.status() >= 500) {
      failedResponses.push(`${response.status()} ${url}`);
    }
  });

  await page.goto('/data');

  await expect(
    page.getByRole('heading', { name: '데이터와 파일' })
  ).toBeVisible();
  await expect(
    page
      .getByLabel('선택한 파일 자산 상세')
      .getByRole('heading', { name: 'roadmap.md' })
  ).toBeVisible();
  await expect(
    page.getByText('쓰기 가능 · 충돌 검사용 ETag 준비')
  ).toBeVisible();
  await expect(
    page.getByText('문서 자산 근거를 불러오지 못했습니다.')
  ).toHaveCount(0);
  await expect(
    page.getByText('WebDAV 원본 계정 목록을 확인하지 못했습니다.')
  ).toHaveCount(0);

  const intentResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith('/api/webdav/writeback-intent');
  });
  await page.getByRole('button', { name: 'WebDAV 반영 의도 점검' }).click();
  const webdavIntentResponse = await intentResponse;
  expect(webdavIntentResponse.status()).toBeLessThan(400);
  expect(webdavIntentResponse.request().headers().authorization).toBeUndefined();

  const materializationResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith(
      '/api/data/documents/doc_repository_ready/webdav-materialization-intent'
    );
  });
  await page
    .getByRole('button', { name: '고객 WebDAV에 문서 쓰기' })
    .click();
  await page
    .getByRole('alertdialog', { name: '고객 WebDAV에 문서를 쓰시겠습니까?' })
    .getByRole('button', { name: 'WebDAV 쓰기 확인' })
    .click();
  const webdavMaterializationResponse = await materializationResponse;
  expect(webdavMaterializationResponse.status()).toBeLessThan(400);
  expect(
    webdavMaterializationResponse.request().headers().authorization
  ).toBeUndefined();

  expect(failedResponses).toEqual([]);
});
