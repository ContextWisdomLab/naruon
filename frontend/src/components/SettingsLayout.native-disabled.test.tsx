/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { SettingsLayout } from './SettingsLayout';
import React from 'react';

describe('SettingsLayout native disabled behavior', () => {
  it('should not contain aria-disabled when the native disabled attribute is used', () => {
    const { container } = render(<SettingsLayout />);
    const buttons = container.querySelectorAll('button[disabled]');
    buttons.forEach((button) => {
      expect(button.hasAttribute('aria-disabled')).toBe(false);
    });
  });
});
