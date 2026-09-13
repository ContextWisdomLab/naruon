/* @vitest-environment jsdom */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { SettingsLayout } from './SettingsLayout';
import React, { act } from 'react';
import { createRoot, type Root } from "react-dom/client";

describe('SettingsLayout native disabled behavior', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    container?.remove();
    container = null;
    root = null;
  });

  it('should not contain aria-disabled when the native disabled attribute is used', () => {
    act(() => {
      root?.render(<SettingsLayout />);
    });
    const buttons = container?.querySelectorAll('button[disabled]');
    buttons?.forEach((button) => {
      expect(button.hasAttribute('aria-disabled')).toBe(false);
    });
  });
});
