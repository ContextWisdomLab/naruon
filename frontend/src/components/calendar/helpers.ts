import { calendarDefinitions } from "./constants";
import {
  CalendarConflictDecisionCode,
  CalendarWritebackSource,
  CalendarWritebackIntentResponse,
} from "./types";

export function buildInitialCalendarVisibility() {
  return Object.fromEntries(calendarDefinitions.map((calendar) => [calendar.id, true]));
}

export function isCustomerOwnedWritableSource(source: CalendarWritebackSource) {
  return source.writeback_enabled
    && source.protocol !== 'local'
    && source.capabilities.includes('write');
}

export function getCalendarSourceLabel(index: number) {
  return `일정 원본 ${index + 1}`;
}

export function getProtocolLabel(protocol: string) {
  switch (protocol) {
    case 'caldav':
      return 'CalDAV 원본';
    case 'carddav':
      return 'CardDAV 원본';
    case 'webdav':
      return 'WebDAV 원본';
    default:
      return '원본 계정';
  }
}

export function getCapabilityLabel(capability: string) {
  switch (capability) {
    case 'read':
      return '읽기';
    case 'write':
      return '일정 반영';
    case 'etag':
      return '충돌 검사';
    default:
      return '원본 기능';
  }
}

export function getEtagLabel(value: string | null) {
  return value ? '충돌 토큰 있음' : '충돌 토큰 대기';
}

export function getIntentProtocolLabel(protocol: string) {
  return `${getProtocolLabel(protocol)} 선택됨`;
}

export function getWritebackModeLabel(mode: CalendarWritebackIntentResponse['writeback_mode']) {
  return mode === 'customer_owned' ? '고객 원본 계정 반영' : '원본 계정 확인 필요';
}

export function getProviderExecutionLabel(result: CalendarWritebackIntentResponse) {
  if (result.provider_write_executed) return '외부 원본 쓰기 완료';
  if (result.retry_item_uid || result.status === 'queued') return '커넥터 실행 요청 접수';
  if (result.error_code) return '커넥터 실행 실패';
  return '의도만 기록';
}

export function getProviderRetryLabel(result: CalendarWritebackIntentResponse) {
  if (result.retry_item_uid || result.status === 'queued') return '재시도 대기';
  if (result.provider_write_executed) return '재시도 없음';
  return '실행 요청 없음';
}

export function getConflictDecisionLabel(decisionCode: CalendarConflictDecisionCode): string {
  switch (decisionCode) {
    case 'available':
      return '진행 가능';
    case 'blocked':
      return '이중 예약 차단';
    case 'review_required':
      return '검토 필요';
    default: {
      const exhaustiveCheck: never = decisionCode;
      return exhaustiveCheck;
    }
  }
}

export function getConflictNextActionLabel(decisionCode: CalendarConflictDecisionCode): string {
  switch (decisionCode) {
    case 'available':
      return '이 시간은 비어 있습니다. 일정을 계속 진행하세요.';
    case 'blocked':
      return '확정된 일정이 겹칩니다. 다른 시간을 고르거나 기존 확정 일정을 먼저 조정하세요.';
    case 'review_required':
      return '잠정 일정이 겹칩니다. 잠정 일정을 조정하거나 유지할지 확인한 뒤 진행하세요.';
    default: {
      const exhaustiveCheck: never = decisionCode;
      return exhaustiveCheck;
    }
  }
}

export function getApiErrorStatus(error: unknown) {
  const shapedError = error as { status?: unknown; response?: { status?: unknown } } | null;
  if (typeof shapedError?.status === 'number') return shapedError.status;
  if (typeof shapedError?.response?.status === 'number') return shapedError.response.status;
  return null;
}