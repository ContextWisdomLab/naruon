export type CalendarWritebackIntentResponse = {
  workspace_id: string;
  target_source_id: string;
  protocol: string;
  writeback_mode: 'customer_owned';
  requires_if_match: boolean;
  if_match: string | null;
  provenance: Record<string, string>;
  audit_event: string;
  provider_write_executed: boolean;
  status: string;
  runner_request_id: string | null;
  provider_status: number | null;
  error_code: string | null;
  retry_item_uid?: string | null;
};

export type CalendarWritebackSource = {
  source_id: string;
  provider: string;
  protocol: 'caldav' | 'carddav' | 'webdav' | 'local';
  owner_id: string;
  organization_id: string | null;
  capabilities: string[];
  writeback_enabled: boolean;
  etag: string | null;
};

export type WritebackStatus = 'idle' | 'loading' | 'success' | 'no_source' | 'conflict' | 'auth' | 'error';

export type CalendarWritebackActionKey = 'create' | 'update' | 'execute';

export type CalendarConflictDecisionCode = 'available' | 'blocked' | 'review_required';

export type CalendarConflictEvidence = {
  commitment_id: string;
  start_at: string;
  end_at: string;
  status: 'confirmed' | 'tentative' | 'desired' | 'cancelled';
};

export type CalendarConflictResponse = {
  decision_code: CalendarConflictDecisionCode;
  reason_code: string;
  conflicts: CalendarConflictEvidence[];
  recommended_action: string;
  policy_version: string;
};

export type CalendarDefinition = {
  id: string;
  name: string;
  colorClass: string;
};

export type CalendarMonthEvent = {
  id: string;
  calendarId: string;
  dayIndex: number;
  time: string;
  title: string;
  source: string;
  description: string;
  monthClassName: string;
  dotClassName: string;
  badgeClassName: string;
  badgeLabel: string;
  duration: string;
  location: string;
};

export type CalendarWeekEvent = {
  id: string;
  calendarId: string;
  day: string;
  title: string;
  source: string;
};

export type CalendarCandidateEvent = {
  id: string;
  calendarId: string;
  title: string;
  source: string;
  mode: string;
};

export type CalendarDetailEvent = CalendarMonthEvent;
