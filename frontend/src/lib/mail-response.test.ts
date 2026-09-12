import { describe, expect, it } from 'vitest';
import { isMailListItem } from './mail-response';

const validMail = { id: 1, subject: null, sender: 'example@example.com', snippet: '' };

describe('mail response boundary', () => {
  it('preserves nullable subjects and optional API display fields', () => {
    expect(isMailListItem(validMail)).toBe(true);
    expect(isMailListItem({ ...validMail, reply_count: null, is_read: false, date: '' })).toBe(true);
  });
  it.each([null, [], {}, 42, { ...validMail, subject: 42 }, { ...validMail, date: {} },
    { ...validMail, reply_count: {} }, { ...validMail, unread: 'false' },
    { ...validMail, id: Number.NaN }, { ...validMail, sender: null }, { ...validMail, snippet: [] },
  ])('rejects malformed mail %j', (mailValue) => {
    expect(isMailListItem(mailValue)).toBe(false);
  });
});
