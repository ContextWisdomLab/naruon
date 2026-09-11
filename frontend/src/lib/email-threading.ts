export interface ThreadEmailData {
  id: number;
  subject: string | null;
  sender: string;
  reply_to?: string | null;
  body: string;
  date?: string | null;
  thread_id?: string | null;
  message_id?: string | null;
  in_reply_to?: string | null;
  references?: string | null;
}

export interface ReplyPayload {
  to: string;
  subject: string;
  body: string;
  in_reply_to?: string;
  references?: string;
}

function extractMailbox(value: string): string {
  const angleMatch = value.match(/<([^>]+)>/);
  return (angleMatch?.[1] ?? value).trim();
}

function buildReferences(email: ThreadEmailData): string | undefined {
  const references = email.references?.trim();
  const messageId = email.message_id?.trim();

  if (!references) return messageId || undefined;
  if (!messageId) return references;

  const normalizedMessageId = messageId.replace(/^<|>$/g, "");
  const referenceTokens =
    references.match(/<[^>]+>/g)?.map((token) => token.replace(/^<|>$/g, "")) ??
    references.split(/\s+/).map((token) => token.replace(/^<|>$/g, ""));

  if (referenceTokens.includes(normalizedMessageId)) return references;

  return `${references} ${messageId}`;
}

export function formatEmailDate(value?: string | null): string {
  if (!value) return "Unknown date";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown date";

  return date.toLocaleString();
}

export function buildThreadUrl(apiUrl: string, threadId: string): string {
  // If no base URL is required (handled by apiClient), return relative path
  if (!apiUrl) {
    return `/api/emails/thread/${encodeURIComponent(threadId)}`;
  }
  return `${apiUrl}/api/emails/thread/${encodeURIComponent(threadId)}`;
}

export function getConversationMessages<T extends ThreadEmailData>(
  selectedEmail: T,
  threadEmails: T[],
): T[] {
  const hasSelectedEmail = threadEmails.some(
    (threadEmail) =>
      threadEmail.id === selectedEmail.id ||
      (!!selectedEmail.message_id && threadEmail.message_id === selectedEmail.message_id),
  );

  return hasSelectedEmail ? threadEmails : [selectedEmail];
}

export function buildReplyPayload(
  email: ThreadEmailData,
  draft: string,
): ReplyPayload {
  const to = email.reply_to?.trim()
    ? extractMailbox(email.reply_to)
    : extractMailbox(email.sender);
  const subject = email.subject?.startsWith("Re:")
    ? email.subject
    : `Re: ${email.subject || ""}`;
  const references = buildReferences(email);

  return {
    to,
    subject,
    body: draft,
    in_reply_to: email.message_id || undefined,
    references,
  };
}
