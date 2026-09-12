/* @vitest-environment jsdom */
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MobileCalendarPanel, MobileSearchPanel } from './mobile-workspace-panels';

function jsonResponse(body: unknown, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? 'OK' : 'Server Error',
    json: async () => body,
  } as Response;
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe('mobile workspace API panels', () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) {
      act(() => root?.unmount());
    }
    root = null;
    container?.remove();
    container = null;
    vi.unstubAllGlobals();
  });

  it('renders search results returned by the API', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      results: [{
        id: 1,
        subject: 'Q2 출시 계획 및 우선순위 조정',
        sender: '김지현 PM',
        date: '2026-05-11T09:30:00Z',
        snippet: 'Q2 출시 계획과 우선순위 조정 요청입니다.',
      }],
    })));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<MobileSearchPanel />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain('Q2 출시 계획 및 우선순위 조정');
    expect(container.textContent).not.toContain('맥락 검색 결과를 불러오는 중입니다.');
    expect(fetch).toHaveBeenCalledWith('/api/search', expect.objectContaining({ method: 'POST' }));
  });

  it('normalizes unsafe email result text before rendering', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      results: [{
        id: 1,
        subject: '\u0001Q2 출시\u0002',
        sender: '김\u0003지현 PM',
        date: '2026-05-11T09:30:00Z',
        snippet: '요청\u0004내용입니다.',
      }],
    })));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<MobileSearchPanel />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain('�Q2 출시�');
    expect(container.textContent).toContain('김�지현 PM');
    expect(container.textContent).toContain('요청�내용입니다.');
    expect(container.textContent).not.toContain('\u0001');
  });

  it('renders the calendar empty state when the API has no candidates', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ results: [] })));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<MobileCalendarPanel />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain('일정 후보가 없습니다.');
  });

  it.each([false, true])('renders the search error state for malformed or failed response (HTTP OK: %s)', async (httpOk) => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ results: [null] }, httpOk)));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<MobileSearchPanel />);
    });
    await flushAsyncWork();

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('맥락 검색을 불러오지 못했습니다.');
  });

  it('returns to loading instead of showing stale results when the search panel is reactivated', async () => {
    let resolveFirst!: (value: Response) => void;
    const firstRequest = new Promise<Response>((resolve) => {
      resolveFirst = resolve;
    });
    const secondRequest = new Promise<Response>(() => undefined);
    vi.stubGlobal('fetch', vi.fn()
      .mockReturnValueOnce(firstRequest)
      .mockReturnValueOnce(secondRequest));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<MobileSearchPanel />);
    });
    await act(async () => {
      resolveFirst(jsonResponse({
        results: [{
          id: 1,
          subject: '이전 맥락 검색 결과',
          sender: '김지현 PM',
          date: '2026-05-11T09:30:00Z',
          snippet: '이전 요청 결과입니다.',
        }],
      }));
    });
    await flushAsyncWork();
    expect(container.textContent).toContain('이전 맥락 검색 결과');

    await act(async () => {
      root?.render(<div />);
    });
    await act(async () => {
      root?.render(<MobileSearchPanel />);
    });
    await flushAsyncWork();

    expect(container.textContent).toContain('맥락 검색 결과를 불러오는 중입니다.');
    expect(container.textContent).not.toContain('이전 맥락 검색 결과');
  });
});
