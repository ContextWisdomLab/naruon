/** Validate consumed mail fields before publishing inbox, sent, or search data. */
export function isMailListItem(itemValue: unknown): boolean {
  if (typeof itemValue !== 'object' || itemValue === null || Array.isArray(itemValue)) return false;
  const mailRecord = itemValue as Record<string, unknown>;
  return typeof mailRecord.id === 'number' && Number.isSafeInteger(mailRecord.id)
    && (mailRecord.subject === null || typeof mailRecord.subject === 'string')
    && typeof mailRecord.sender === 'string' && typeof mailRecord.snippet === 'string'
    && (mailRecord.date === undefined || typeof mailRecord.date === 'string')
    && (mailRecord.reply_count === undefined || mailRecord.reply_count === null
      || (typeof mailRecord.reply_count === 'number' && Number.isSafeInteger(mailRecord.reply_count)))
    && ['unread', 'is_read', 'has_draft', 'is_self_sent', 'requires_reply', 'schedule_conflict']
      .every((fieldName) => mailRecord[fieldName] === undefined || typeof mailRecord[fieldName] === 'boolean');
}
