"use client";

import { Activity, Settings, User, Mail, Bell, Shield, Smartphone, Monitor, AlertCircle, RefreshCw, Bot, Cpu, Network, Plus, CheckCircle2, Loader2 } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import type { SessionClaims } from '@/lib/session-cookie';
import { clearOidcSession, getOidcBrowserConfig, startOidcLogin } from '@/lib/oidc-session';
import { useWorkspaceStartupView, setWorkspaceStartupView } from '@/lib/workspace-preferences';
import { useEffect, useRef, useState, type RefObject } from 'react';

export type SettingsTab = '워크스페이스' | '멤버' | 'AI 모델' | '연결 계정' | '알림' | '자동화' | '결제' | '개발자';
const EMPTY_SESSION_CLAIMS: SessionClaims = {
  userId: null,
  organizationId: null,
  workspaceId: null,
};

interface RunnerConfig {
  workspace_id: string;
  configured: boolean;
  fingerprint: string | null;
  updated_at: string | null;
  connector_manifest: {
    role: string;
    network_mode: string;
    control_plane_domain: string;
    local_protocols: string[];
    prohibited_roles: string[];
    runner_usage: string;
  };
}

interface RunnerRotateResponse {
  workspace_id: string;
  configured: boolean;
  fingerprint: string | null;
  updated_at: string | null;
  connector_manifest: RunnerConfig['connector_manifest'];
}

interface OperationalSignal {
  signal_key: string;
  display_name: string;
  state: string;
  evidence_source: string;
  detail: string;
  provider_write_executed: boolean;
}

interface ConnectorSignalEvent {
  event_uid: string;
  signal_key: string;
  state_code: string;
  detail_text: string | null;
  observed_at: string;
}

interface OperationalSignalsResponse {
  workspace_id: string;
  audit_event: string;
  telemetry: {
    prometheus_metrics_enabled: boolean;
    otel_traces_enabled: boolean;
    otel_endpoint_configured: boolean;
    otel_endpoint_host: string | null;
  };
  connector: {
    workspace_id: string;
    registration_state: 'registration_configured' | 'not_registered';
    connection_state: 'connected' | 'not_connected';
    active_connection_count: number;
    control_plane_domain: string;
    network_mode: string;
    runner_usage: string;
    local_protocols: string[];
    last_heartbeat_at: string | null;
    last_disconnect_at: string | null;
    queue_depth_state: 'clear' | 'backlog' | 'degraded';
    queue_depth: {
      pending_count: number;
      running_count: number;
      failed_count: number;
      total_count: number;
      next_retry_at: string | null;
    };
    recent_events: ConnectorSignalEvent[];
  };
  signals: OperationalSignal[];
}

interface AccountConfig {
  user_id: string;
  smtp_server: string | null;
  smtp_port: number | null;
  smtp_username: string | null;
  has_smtp_password: boolean;
  imap_server: string | null;
  imap_port: number | null;
  imap_username: string | null;
  has_imap_password: boolean;
  pop3_server: string | null;
  pop3_port: number | null;
  pop3_username: string | null;
  has_pop3_password: boolean;
  oauth_client_id: string | null;
  oauth_redirect_uri: string | null;
  has_oauth_client_secret: boolean;
}

interface AccountConfigUpdate {
  smtp_server: string | null;
  smtp_port: number | null;
  smtp_username: string | null;
  smtp_password?: string;
  imap_server: string | null;
  imap_port: number | null;
  imap_username: string | null;
  imap_password?: string;
  pop3_server: string | null;
  pop3_port: number | null;
  pop3_username: string | null;
  pop3_password?: string;
  oauth_client_id: string | null;
  oauth_client_secret?: string;
  oauth_redirect_uri: string | null;
}

interface CalendarWritebackSource {
  source_id: string;
  provider: string;
  protocol: string;
  owner_id: string;
  organization_id: string | null;
  capabilities: string[];
  writeback_enabled: boolean;
  etag: string | null;
}

interface WebdavAccount {
  source_id: string;
  display_label: string;
  writeback_enabled: boolean;
}

interface LLMProviderConfig {
  id: number;
  name: string;
  provider_type: string;
  base_url: string | null;
  model_identifier: string | null;
  embedding_model: string | null;
  is_active: boolean;
  configured: boolean;
  fingerprint: string | null;
  updated_at: string;
}

interface AccountFormState {
  smtpServer: string;
  smtpPort: string;
  smtpUsername: string;
  imapServer: string;
  imapPort: string;
  imapUsername: string;
  pop3Server: string;
  pop3Port: string;
  pop3Username: string;
  oauthClientId: string;
  oauthRedirectUri: string;
}

interface ModelProviderFormState {
  name: string;
  providerType: string;
  baseUrl: string;
  modelIdentifier: string;
  embeddingModel: string;
  isActive: boolean;
}

interface AccountSecretFormValues {
  smtpPassword: string;
  imapPassword: string;
  pop3Password: string;
  oauthClientSecret: string;
}

const emptyAccountForm: AccountFormState = {
  smtpServer: '',
  smtpPort: '',
  smtpUsername: '',
  imapServer: '',
  imapPort: '',
  imapUsername: '',
  pop3Server: '',
  pop3Port: '',
  pop3Username: '',
  oauthClientId: '',
  oauthRedirectUri: '',
};

const commercialModelFormDefaults: ModelProviderFormState = {
  name: '상용 API 기본 모델',
  providerType: 'openai',
  baseUrl: 'https://api.openai.com/v1',
  modelIdentifier: 'gpt-4o',
  embeddingModel: 'text-embedding-3-small',
  isActive: true,
};

const localModelFormDefaults: ModelProviderFormState = {
  name: 'Local Gemma4',
  providerType: 'ollama',
  baseUrl: 'http://ollama:11434/v1',
  modelIdentifier: 'gemma4:e2b-it-qat',
  embeddingModel: 'embeddinggemma',
  isActive: true,
};

const embeddingModelOptions = [
  { value: 'text-embedding-3-small', label: 'text-embedding-3-small', detail: 'OpenAI (1536차원)' },
  { value: 'text-embedding-3-large', label: 'text-embedding-3-large', detail: 'OpenAI (3072차원)' },
  { value: 'nomic-embed-text', label: 'nomic-embed-text', detail: '로컬 Ollama' },
  { value: 'embeddinggemma', label: 'embeddinggemma', detail: 'Gemma 임베딩 · 로컬 Ollama' },
];

// Note: Passwords and secrets are intentionally cleared here and never stored in plain text client-side.
// We only collect them from the user temporarily when updating credentials, sending them directly via HTTPS.
function toAccountForm(config: AccountConfig): AccountFormState {
  return {
    smtpServer: config.smtp_server ?? '',
    smtpPort: config.smtp_port?.toString() ?? '',
    smtpUsername: config.smtp_username ?? '',
    imapServer: config.imap_server ?? '',
    imapPort: config.imap_port?.toString() ?? '',
    imapUsername: config.imap_username ?? '',
    pop3Server: config.pop3_server ?? '',
    pop3Port: config.pop3_port?.toString() ?? '',
    pop3Username: config.pop3_username ?? '',
    oauthClientId: config.oauth_client_id ?? '',
    oauthRedirectUri: config.oauth_redirect_uri ?? '',
  };
}

function optionalText(value: string) {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function optionalPort(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/^\d+$/.test(trimmed)) return null;
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) && parsed >= 1 && parsed <= 65535 ? parsed : null;
}

function buildAccountUpdate(form: AccountFormState, secrets: AccountSecretFormValues): AccountConfigUpdate {
  const update: AccountConfigUpdate = {
    smtp_server: optionalText(form.smtpServer),
    smtp_port: optionalPort(form.smtpPort),
    smtp_username: optionalText(form.smtpUsername),
    imap_server: optionalText(form.imapServer),
    imap_port: optionalPort(form.imapPort),
    imap_username: optionalText(form.imapUsername),
    pop3_server: optionalText(form.pop3Server),
    pop3_port: optionalPort(form.pop3Port),
    pop3_username: optionalText(form.pop3Username),
    oauth_client_id: optionalText(form.oauthClientId),
    oauth_redirect_uri: optionalText(form.oauthRedirectUri),
  };

  const smtpPassword = optionalText(secrets.smtpPassword);
  if (smtpPassword) update.smtp_password = smtpPassword;
  const imapPassword = optionalText(secrets.imapPassword);
  if (imapPassword) update.imap_password = imapPassword;
  const pop3Password = optionalText(secrets.pop3Password);
  if (pop3Password) update.pop3_password = pop3Password;
  const oauthClientSecret = optionalText(secrets.oauthClientSecret);
  if (oauthClientSecret) update.oauth_client_secret = oauthClientSecret;

  return update;
}

function buildProviderCreate(form: ModelProviderFormState, apiKeyValue: string) {
  const payload: {
    name: string;
    provider_type: string;
    base_url: string | null;
    model_identifier: string | null;
    embedding_model: string | null;
    api_key?: string;
    is_active: boolean;
  } = {
    name: optionalText(form.name) ?? form.modelIdentifier,
    provider_type: optionalText(form.providerType) ?? 'openai',
    base_url: optionalText(form.baseUrl),
    model_identifier: optionalText(form.modelIdentifier),
    embedding_model: optionalText(form.embeddingModel),
    is_active: form.isActive,
  };

  const apiKey = optionalText(apiKeyValue);
  if (apiKey) payload.api_key = apiKey;
  return payload;
}

function readInputValue(ref: RefObject<HTMLInputElement | null>) {
  return ref.current?.value ?? '';
}

function clearInputValue(ref: RefObject<HTMLInputElement | null>) {
  if (ref.current) ref.current.value = '';
}

function formatEndpoint(host: string | null | undefined, port: number | null | undefined) {
  if (!host) return '미설정';
  return port ? `${host}:${port}` : host;
}

const settingsTabs: { id: SettingsTab; icon: typeof Monitor }[] = [
  { id: '워크스페이스', icon: Monitor },
  { id: '멤버', icon: User },
  { id: 'AI 모델', icon: Bot },
  { id: '연결 계정', icon: Mail },
  { id: '알림', icon: Bell },
  { id: '자동화', icon: Settings },
  { id: '결제', icon: Shield },
  { id: '개발자', icon: Smartphone },
];

function getWritebackReadinessLabel(writebackEnabled: boolean) {
  return writebackEnabled ? '쓰기 의도 가능' : '읽기 전용';
}

function getEtagReadinessLabel(etag: string | null | undefined) {
  return etag ? '충돌 검사용 ETag 준비' : 'ETag 확인 필요';
}

function getCapabilityLabel(capability: string) {
  switch (capability) {
    case 'read':
      return '읽기';
    case 'write':
      return '쓰기';
    case 'etag':
      return '충돌 검사';
    default:
      return '원본 기능';
  }
}

function getWebdavAccountLabel(account: WebdavAccount, index: number) {
  const label = account.display_label.trim();
  if (!label || label.includes(account.source_id) || /^WebDAV source/i.test(label)) {
    return `WebDAV 저장소 ${index + 1}`;
  }
  return label;
}

function getConnectorStateLabel(state: string) {
  switch (state) {
    case 'connected':
      return '연결됨';
    case 'not_connected':
      return '미연결';
    case 'enabled':
      return '활성';
    case 'instrumentation_pending':
      return '계측 준비';
    case 'not_configured':
      return '미설정';
    case 'heartbeat':
      return '하트비트 수신';
    default:
      return '상태 확인';
  }
}

function getRegistrationLabel(configured: boolean | undefined) {
  return configured ? '등록됨' : '미등록';
}

function getOperationalEvidenceLabel(evidenceSource: string) {
  if (/runner/i.test(evidenceSource)) return '서버 관측 runner 신호';
  if (/provider|adapter/i.test(evidenceSource)) return '연결 어댑터 근거';
  return '운영 신호 근거';
}

function getNetworkModeLabel(networkMode: string) {
  return networkMode === 'outbound_only' ? 'Outbound only' : '제한된 연결';
}

function getRunnerUsageLabel(runnerUsage: string) {
  return runnerUsage === 'ci_smoke_only' ? '검증용 연결' : '운영 연결';
}

function getProhibitedRoleLabel(role: string) {
  switch (role) {
    case 'smtp_server':
      return 'SMTP 서버 역할 금지';
    case 'imap_server':
      return 'IMAP 서버 역할 금지';
    case 'mx_host':
      return 'MX 호스트 역할 금지';
    default:
      return '금지 역할';
  }
}

function getConnectorEventDetail(event: ConnectorSignalEvent) {
  if (event.state_code === 'heartbeat') return '서버가 runner 하트비트를 관측했습니다.';
  if (event.state_code === 'connected') return '서버가 outbound runner 연결을 관측했습니다.';
  if (event.state_code === 'disconnected') return '서버가 runner 연결 종료를 관측했습니다.';
  return event.detail_text ? '서버 관측 이벤트가 기록되었습니다.' : '이벤트 상세가 아직 기록되지 않았습니다.';
}

function getOperationalSignalDetail(signal: OperationalSignal) {
  if (signal.signal_key === 'connector_heartbeat') return '서버가 활성 outbound runner 상태를 확인합니다.';
  if (signal.signal_key === 'writeback_retry_queue') return '서버가 provider writeback 재시도 큐 상태를 집계합니다.';
  if (signal.signal_key === 'sync_lag') return '원본 connector 작업이 동기화 지연 신호를 기록하면 표시합니다.';
  return signal.detail ? '운영 신호 상태를 확인합니다.' : '상세 근거가 아직 기록되지 않았습니다.';
}

function getQueueDepthLabel(state: OperationalSignalsResponse['connector']['queue_depth_state']) {
  if (state === 'degraded') return '조치 필요';
  if (state === 'backlog') return '대기 중';
  return '비어 있음';
}

function getProviderTypeLabel(providerType: string) {
  switch (providerType.toLowerCase()) {
    case 'openai':
      return 'OpenAI 호환';
    case 'anthropic':
      return 'Anthropic';
    case 'gemini':
      return 'Google Gemini';
    case 'ollama':
      return '로컬 Ollama';
    case 'vllm':
      return '로컬 vLLM';
    default:
      return 'OpenAI-compatible';
  }
}

function getProviderEndpointLabel(provider: LLMProviderConfig) {
  if (provider.base_url) return provider.base_url;
  return provider.provider_type === 'openai' ? '기본 OpenAI API 엔드포인트' : '기본 제공자 엔드포인트';
}

const settingsDetailSurfaces: Partial<Record<SettingsTab, {
  heading: string;
  copy: string;
  items: { title: string; detail: string; status: string }[];
}>> = {
  멤버: {
    heading: '멤버와 역할',
    copy: '조직 관리자, 보안 담당자, 팀 리드, 개인 사용자의 역할과 ABAC 조건을 한 화면에서 점검합니다.',
    items: [
      { title: '관리자 경계', detail: 'platform_admin과 organization_admin 권한을 분리하고 customer-policy deny를 우선 적용합니다.', status: 'RBAC/ABAC' },
      { title: '팀 스코프', detail: '그룹/본부/팀 단위 멤버십과 workspace scope를 감사 로그와 함께 추적합니다.', status: '조직 계층' },
      { title: '초대 검토', detail: '외부 공유와 신규 초대는 보안 정책, consent, data-region 조건을 통과해야 합니다.', status: '정책 점검' },
    ],
  },
  알림: {
    heading: '알림 정책',
    copy: '메일 회신 추적, 일정 충돌, writeback conflict, connector health 이벤트를 사용자별 채널 정책으로 정리합니다.',
    items: [
      { title: '답변 추적', detail: '보낸 메일 답변 기한이 지나면 홈 대기 작업과 알림 큐에 같은 사건으로 표시합니다.', status: '메일 연동' },
      { title: '일정 충돌', detail: 'CalDAV writeback 후보가 충돌하거나 ETag가 맞지 않으면 재확인 알림을 생성합니다.', status: '캘린더' },
      { title: 'Connector health', detail: 'self-hosted connector heartbeat, sync lag, provider throttling을 운영 알림으로 묶습니다.', status: '운영' },
    ],
  },
  자동화: {
    heading: '자동화 규칙',
    copy: '메일, 일정, 실행 항목, 프로젝트 상태를 source-linked rule로 연결하되 provider write는 명시적 intent로 남깁니다.',
    items: [
      { title: '메일에서 작업 생성', detail: '실행 항목을 ticket task로 만들고 원본 message/thread provenance를 유지합니다.', status: 'source-linked' },
      { title: '캘린더 writeback', detail: 'AI가 정리한 일정은 source capability와 owner policy를 확인한 뒤 원천 계정에 반영합니다.', status: 'intent-first' },
      { title: '지식 정리', detail: '내가 나에게 보낸 메일은 개인 지식 후보로 분류하고 연결 프로젝트를 제안합니다.', status: 'knowledge' },
    ],
  },
  결제: {
    heading: '결제와 사용량',
    copy: 'B2C, SOHO, 조직 계정이 같은 tenant 구조에서 quota, connector, AI 사용량을 분리해 봅니다.',
    items: [
      { title: '워크스페이스 quota', detail: '메일 본문 저장소가 아니라 metadata/index/action intent 중심으로 사용량을 계산합니다.', status: 'data sovereignty' },
      { title: 'Connector seat', detail: '사내망 connector는 조직 스코프별 등록 토큰과 운영 감사 대상으로 계산합니다.', status: 'B2B2C' },
      { title: 'AI 사용량', detail: '프롬프트 실행, 평가, 맥락 종합, writeback 제안을 provider별 비용 항목으로 분리합니다.', status: 'BYOK' },
    ],
  },
};

export function SettingsLayout() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('워크스페이스');
  const [runnerConfig, setRunnerConfig] = useState<RunnerConfig | null>(null);
  const [runnerError, setRunnerError] = useState<string | null>(null);
  const [runnerLoading, setRunnerLoading] = useState(true);
  const [runnerRotating, setRunnerRotating] = useState(false);
  const [runnerRotateError, setRunnerRotateError] = useState<string | null>(null);
  const [runnerTokenIssued, setRunnerTokenIssued] = useState(false);
  const [operationalSignals, setOperationalSignals] = useState<OperationalSignalsResponse | null>(null);
  const [operationalError, setOperationalError] = useState<string | null>(null);
  const [operationalLoading, setOperationalLoading] = useState(true);
  const [accountConfig, setAccountConfig] = useState<AccountConfig | null>(null);
  const [accountForm, setAccountForm] = useState<AccountFormState>(emptyAccountForm);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [accountStatus, setAccountStatus] = useState<string | null>(null);
  const [accountLoading, setAccountLoading] = useState(true);
  const [accountSaving, setAccountSaving] = useState(false);
  const [calendarSources, setCalendarSources] = useState<CalendarWritebackSource[]>([]);
  const [webdavAccounts, setWebdavAccounts] = useState<WebdavAccount[]>([]);
  const [sourceReadinessLoading, setSourceReadinessLoading] = useState(true);
  const [sourceReadinessError, setSourceReadinessError] = useState<string | null>(null);
  const [modelProviders, setModelProviders] = useState<LLMProviderConfig[]>([]);
  const [modelProvidersLoading, setModelProvidersLoading] = useState(true);
  const [modelProvidersError, setModelProvidersError] = useState<string | null>(null);
  const [modelProviderStatus, setModelProviderStatus] = useState<string | null>(null);
  const [commercialModelForm, setCommercialModelForm] = useState<ModelProviderFormState>(commercialModelFormDefaults);
  const [localModelForm, setLocalModelForm] = useState<ModelProviderFormState>(localModelFormDefaults);
  const [commercialModelSaving, setCommercialModelSaving] = useState(false);
  const [localModelSaving, setLocalModelSaving] = useState(false);
  const [selectedEmbeddingProviderId, setSelectedEmbeddingProviderId] = useState<number | null>(null);
  const [selectedEmbeddingModel, setSelectedEmbeddingModel] = useState('embeddinggemma');
  const [embeddingSaving, setEmbeddingSaving] = useState(false);
  const [oidcSessionClaims, setOidcSessionClaims] = useState<SessionClaims>(EMPTY_SESSION_CLAIMS);
  const [oidcActionError, setOidcActionError] = useState<string | null>(null);
  const smtpPasswordInputRef = useRef<HTMLInputElement>(null);
  const imapPasswordInputRef = useRef<HTMLInputElement>(null);
  const pop3PasswordInputRef = useRef<HTMLInputElement>(null);
  const oauthClientSecretInputRef = useRef<HTMLInputElement>(null);
  const commercialApiKeyInputRef = useRef<HTMLInputElement>(null);
  const localApiKeyInputRef = useRef<HTMLInputElement>(null);
  const startupView = useWorkspaceStartupView();
  const oidcBrowserConfig = getOidcBrowserConfig();
  const connectorManifest = runnerConfig?.connector_manifest;
  const detailSurface = settingsDetailSurfaces[activeTab];
  const connectorEvents = operationalSignals?.connector.recent_events ?? [];
  const activeModelProvider = modelProviders.find((provider) => provider.is_active) ?? modelProviders[0] ?? null;
  const selectedEmbeddingProvider = modelProviders.find((provider) => provider.id === selectedEmbeddingProviderId) ?? activeModelProvider;
  const accountReady = !accountLoading && !accountError && accountConfig !== null;
  const oauthAppConfigured = Boolean(
    accountConfig?.oauth_client_id
      && accountConfig?.oauth_redirect_uri
      && accountConfig?.has_oauth_client_secret,
  );
  const oauthConsentState = oauthAppConfigured ? '앱 설정 완료, 사용자 consent 대기' : '앱 설정 미완료';
  const accountProtocols = [
    {
      label: 'SMTP 송신',
      endpoint: formatEndpoint(accountConfig?.smtp_server, accountConfig?.smtp_port),
      identity: accountConfig?.smtp_username ?? '발신 계정 미설정',
      secretReady: accountConfig?.has_smtp_password ?? false,
      detail: '메일 발송과 보낸 메일 답변 추적에 사용합니다.',
    },
    {
      label: 'IMAP 수신',
      endpoint: formatEndpoint(accountConfig?.imap_server, accountConfig?.imap_port),
      identity: accountConfig?.imap_username ?? '수신 계정 미설정',
      secretReady: accountConfig?.has_imap_password ?? false,
      detail: '받은편지함, 스레드, self-sent 지식 후보를 읽습니다.',
    },
    {
      label: 'POP3 반입',
      endpoint: formatEndpoint(accountConfig?.pop3_server, accountConfig?.pop3_port),
      identity: accountConfig?.pop3_username ?? '반입 계정 미설정',
      secretReady: accountConfig?.has_pop3_password ?? false,
      detail: '레거시 메일함과 ZIP 반입 중복 정리에 사용합니다.',
    },
    {
      label: 'OAuth 로그인',
      endpoint: accountConfig?.oauth_client_id ?? '미설정',
      identity: accountConfig?.oauth_redirect_uri ?? 'redirect URI 미설정',
      secretReady: accountConfig?.has_oauth_client_secret ?? false,
      detail: `지원 provider에서는 비밀번호 대신 OAuth consent를 사용합니다. ${oauthConsentState}`,
    },
  ];

  const updateAccountField = (field: keyof AccountFormState, value: string) => {
    setAccountForm((current) => ({ ...current, [field]: value }));
    setAccountStatus(null);
  };

  const clearAccountSecretInputs = () => {
    clearInputValue(smtpPasswordInputRef);
    clearInputValue(imapPasswordInputRef);
    clearInputValue(pop3PasswordInputRef);
    clearInputValue(oauthClientSecretInputRef);
  };

  const handleOidcLogin = async () => {
    setOidcActionError(null);
    try {
      await startOidcLogin({ returnTo: window.location.pathname });
    } catch (error) {
      setOidcActionError(error instanceof Error ? error.message : 'OIDC login failed');
    }
  };

  const handleOidcLogout = async () => {
    setOidcActionError(null);
    try {
      await clearOidcSession({ postLogoutRedirectUri: window.location.origin });
      setOidcSessionClaims(EMPTY_SESSION_CLAIMS);
    } catch (error) {
      setOidcActionError(error instanceof Error ? error.message : 'OIDC logout failed');
    }
  };

  const handleAccountSave = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!accountReady) return;
    setAccountSaving(true);
    setAccountError(null);
    setAccountStatus(null);

    try {
      const savedConfig = await apiClient.put<AccountConfig>('/api/accounts/config', buildAccountUpdate(accountForm, {
        smtpPassword: readInputValue(smtpPasswordInputRef),
        imapPassword: readInputValue(imapPasswordInputRef),
        pop3Password: readInputValue(pop3PasswordInputRef),
        oauthClientSecret: readInputValue(oauthClientSecretInputRef),
      }));
      setAccountConfig(savedConfig);
      setAccountForm(toAccountForm(savedConfig));
      clearAccountSecretInputs();
      setAccountStatus('계정 설정을 저장했습니다. 저장된 secret은 응답에 노출되지 않습니다.');
    } catch (error) {
      const message = error instanceof Error ? error.message : '계정 설정을 저장할 수 없습니다.';
      setAccountError(message);
    } finally {
      setAccountSaving(false);
    }
  };

  const updateCommercialModelField = (field: keyof ModelProviderFormState, value: string | boolean) => {
    setCommercialModelForm((current) => ({ ...current, [field]: value }));
    setModelProviderStatus(null);
  };

  const updateLocalModelField = (field: keyof ModelProviderFormState, value: string | boolean) => {
    setLocalModelForm((current) => ({ ...current, [field]: value }));
    setModelProviderStatus(null);
  };

  const createModelProvider = async (
    event: React.FormEvent<HTMLFormElement>,
    form: ModelProviderFormState,
    options: {
      setSaving: (saving: boolean) => void;
      apiKeyRef: RefObject<HTMLInputElement | null>;
      successMessage: string;
    },
  ) => {
    event.preventDefault();
    options.setSaving(true);
    setModelProvidersError(null);
    setModelProviderStatus(null);

    try {
      const created = await apiClient.post<LLMProviderConfig>('/api/llm-providers', buildProviderCreate(form, readInputValue(options.apiKeyRef)));
      setModelProviders((current) => [created, ...current.filter((provider) => provider.id !== created.id)]);
      setSelectedEmbeddingProviderId(created.id);
      setSelectedEmbeddingModel(created.embedding_model ?? form.embeddingModel);
      clearInputValue(options.apiKeyRef);
      setModelProviderStatus(options.successMessage);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'AI 모델 설정을 저장할 수 없습니다.';
      setModelProvidersError(message);
    } finally {
      options.setSaving(false);
    }
  };

  const handleEmbeddingModelSave = async () => {
    const providerId = selectedEmbeddingProvider?.id;
    if (!providerId) return;

    setEmbeddingSaving(true);
    setModelProvidersError(null);
    setModelProviderStatus(null);

    try {
      const updated = await apiClient.put<LLMProviderConfig>(`/api/llm-providers/${providerId}`, {
        embedding_model: selectedEmbeddingModel,
      });
      setModelProviders((current) => current.map((provider) => (provider.id === updated.id ? updated : provider)));
      setModelProviderStatus('임베딩 모델 지정을 저장했습니다.');
    } catch (error) {
      const message = error instanceof Error ? error.message : '임베딩 모델 지정을 저장할 수 없습니다.';
      setModelProvidersError(message);
    } finally {
      setEmbeddingSaving(false);
    }
  };

  const handleRunnerTokenRotate = async () => {
    setRunnerRotating(true);
    setRunnerRotateError(null);
    setRunnerTokenIssued(false);

    try {
      const rotated = await apiClient.post<RunnerRotateResponse>('/api/runner-config/rotate', {});
      setRunnerConfig({
        workspace_id: rotated.workspace_id,
        configured: rotated.configured,
        fingerprint: rotated.fingerprint,
        updated_at: rotated.updated_at,
        connector_manifest: rotated.connector_manifest,
      });
      setRunnerTokenIssued(true);
      setRunnerError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : '등록 토큰을 회전할 수 없습니다.';
      setRunnerRotateError(message);
    } finally {
      setRunnerRotating(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    void apiClient
      .getServerSessionClaims()
      .then((claims) => {
        if (!cancelled) setOidcSessionClaims(claims);
      })
      .catch(() => {
        if (!cancelled) setOidcSessionClaims(EMPTY_SESSION_CLAIMS);
      });

    void apiClient
      .get<RunnerConfig>('/api/runner-config')
      .then((config) => {
        if (cancelled) return;
        setRunnerConfig(config);
        setRunnerError(null);
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setRunnerError(error.message || 'Self-hosted connector 설정을 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setRunnerLoading(false);
      });

    void apiClient
      .get<OperationalSignalsResponse>('/api/observability/operational-signals')
      .then((signals) => {
        if (cancelled) return;
        setOperationalSignals(signals);
        setOperationalError(null);
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setOperationalError(error.message || '운영 신호를 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setOperationalLoading(false);
      });

    void apiClient
      .get<AccountConfig>('/api/accounts/config')
      .then((config) => {
        if (cancelled) return;
        setAccountConfig(config);
        setAccountForm(toAccountForm(config));
        setAccountError(null);
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setAccountError(error.message || '계정 설정을 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setAccountLoading(false);
      });

    void Promise.all([
      apiClient.get<CalendarWritebackSource[]>('/api/calendar/writeback-sources'),
      apiClient.get<WebdavAccount[]>('/api/webdav/accounts'),
    ])
      .then(([calendarSourceRows, webdavAccountRows]) => {
        if (cancelled) return;
        setCalendarSources(calendarSourceRows);
        setWebdavAccounts(webdavAccountRows);
        setSourceReadinessError(null);
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setSourceReadinessError(error.message || 'Source readiness를 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setSourceReadinessLoading(false);
      });

    void apiClient
      .get<LLMProviderConfig[]>('/api/llm-providers')
      .then((providers) => {
        if (cancelled) return;
        setModelProviders(providers);
        const activeProvider = providers.find((provider) => provider.is_active) ?? providers[0] ?? null;
        setSelectedEmbeddingProviderId(activeProvider?.id ?? null);
        setSelectedEmbeddingModel(activeProvider?.embedding_model ?? 'embeddinggemma');
        setModelProvidersError(null);
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setModelProvidersError(error.message || 'AI 모델 설정을 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setModelProvidersLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex h-full min-w-0 min-h-0 bg-background text-foreground flex-col overflow-x-hidden">
      <header className="flex h-20 shrink-0 items-center border-b border-border bg-card px-4 md:px-8 overflow-hidden">
        <h1 className="text-xl md:text-2xl font-bold flex shrink-0 items-center gap-3">
          <Settings className="size-6 text-primary" />
          <span className="sm:hidden">설정</span>
          <span className="hidden sm:inline">설정</span>
        </h1>
        <p className="sr-only">Self-hosted Runner</p>
      </header>

      <nav aria-label="설정 섹션" className="md:hidden border-b border-border bg-card px-3 py-2">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {settingsTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`min-h-10 shrink-0 rounded-xl px-4 text-sm font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                activeTab === tab.id
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'bg-background text-muted-foreground hover:bg-secondary hover:text-foreground'
              }`}
            >
              {tab.id}
            </button>
          ))}
        </div>
      </nav>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left Sidebar - Settings Tabs */}
        <aside className="w-64 shrink-0 border-r border-border bg-card overflow-y-auto hidden md:block">
          <div className="p-4 space-y-1">
            {settingsTabs.map((tab) => (
              <button type="button"
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-bold transition-colors ${activeTab === tab.id ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'}`}
              >
                <tab.icon className="size-4" /> {tab.id}
              </button>
            ))}
          </div>
        </aside>

        {/* Main Settings Area */}
        <main className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden p-4 md:p-8 bg-background">
          <div className="max-w-3xl space-y-8">
            
            {activeTab === '워크스페이스' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-bold text-xl">워크스페이스 설정</h2>
                    <p className="text-sm text-muted-foreground mt-1">Naruon의 전반적인 동작과 시작 화면을 설정합니다.</p>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                    <h3 className="font-bold text-lg mb-4">시작 화면 설정</h3>
                    <p className="text-sm text-muted-foreground mb-4">로그인 시 처음 보여질 메인 화면을 선택하세요.</p>
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                      {[
                        { label: '홈', value: 'dashboard', desc: '오늘의 맥락 종합과 실행 항목' },
                        { label: '메일', value: 'email', desc: '인박스 중심으로 확인' },
                        { label: '일정 관리', value: 'calendar', desc: '오늘의 회의와 스케줄 확인' }
                      ].map((view) => (
                        <button type="button"
                          key={view.value}
                          onClick={() => setWorkspaceStartupView(view.value as 'dashboard' | 'email' | 'calendar')}
                          className={`flex flex-col items-start gap-1 rounded-xl border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 ${
                            startupView === view.value
                              ? 'border-primary bg-primary/5 shadow-sm'
                              : 'border-border hover:bg-secondary hover:border-primary/50'
                          }`}
                        >
                          <span className={`font-bold ${startupView === view.value ? 'text-primary' : 'text-foreground'}`}>
                            {view.label}
                          </span>
                          <span className="text-xs text-muted-foreground">{view.desc}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'AI 모델' && (
              <div className="space-y-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="font-bold text-xl">AI 모델 설정</h2>
                    <p className="text-sm text-muted-foreground mt-1">대규모 언어 모델(LLM), 로컬 모델, 임베딩 모델을 signed provider registry에 등록하고 관리합니다.</p>
                  </div>
                  <span className="rounded-full border border-border bg-card px-3 py-1 font-mono text-xs font-bold text-foreground">
                    /api/llm-providers
                  </span>
                </div>

                {modelProvidersLoading ? (
                  <p className="rounded-xl bg-secondary/60 p-3 text-sm font-semibold text-muted-foreground">AI 모델 설정을 불러오는 중입니다.</p>
                ) : null}
                {modelProvidersError ? (
                  <p className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900">{modelProvidersError}</p>
                ) : null}
                {modelProviderStatus ? (
                  <p className="rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-sm font-semibold text-emerald-900">{modelProviderStatus}</p>
                ) : null}

                <section aria-label="등록된 AI 모델" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-bold text-lg">등록된 모델 레지스트리</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        조직 스코프에 저장된 provider만 표시합니다. API key 원문은 응답에 포함되지 않습니다.
                      </p>
                    </div>
                    <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-foreground">
                      {modelProviders.length}개
                    </span>
                  </div>

                  {modelProviders.length > 0 ? (
                    <div className="mt-5 grid gap-3">
                      {modelProviders.map((provider) => (
                        <article key={provider.id} className="rounded-xl border border-border bg-background p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <h4 className="font-bold text-base">{provider.name}</h4>
                                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${provider.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-secondary text-muted-foreground'}`}>
                                  {provider.is_active ? '활성 모델' : '대기 모델'}
                                </span>
                                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${provider.configured ? 'bg-blue-100 text-blue-800' : 'bg-amber-100 text-amber-900'}`}>
                                  {provider.configured ? '연결됨' : '설정 필요'}
                                </span>
                              </div>
                              <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                                <div>
                                  <dt className="text-xs font-bold text-muted-foreground">제공자 유형</dt>
                                  <dd className="mt-1 break-all font-semibold">{getProviderTypeLabel(provider.provider_type)}</dd>
                                </div>
                                <div>
                                  <dt className="text-xs font-bold text-muted-foreground">연결 엔드포인트</dt>
                                  <dd className="mt-1 break-all font-semibold">{getProviderEndpointLabel(provider)}</dd>
                                </div>
                                <div>
                                  <dt className="text-xs font-bold text-muted-foreground">모델</dt>
                                  <dd className="mt-1 break-all font-semibold">{provider.model_identifier ?? '모델 지정 필요'}</dd>
                                </div>
                                <div>
                                  <dt className="text-xs font-bold text-muted-foreground">임베딩</dt>
                                  <dd className="mt-1 break-all font-semibold">{provider.embedding_model ?? '임베딩 지정 필요'}</dd>
                                </div>
                              </dl>
                            </div>
                            <div className="flex shrink-0 items-center gap-2 rounded-full border border-border px-3 py-1 text-xs font-bold text-muted-foreground">
                              <CheckCircle2 className="size-3.5 text-primary" />
                              {provider.fingerprint ? `Key ${provider.fingerprint}` : '로컬 credential 없음'}
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-5 rounded-xl border border-dashed border-border p-4 text-sm font-semibold text-muted-foreground">
                      등록된 AI 모델이 없습니다. Gemma4 로컬 모델 또는 상용 API 모델을 등록하세요.
                    </p>
                  )}
                </section>

                <div className="grid gap-6 md:grid-cols-2">
                  <form
                    onSubmit={(event) => createModelProvider(event, commercialModelForm, {
                      setSaving: setCommercialModelSaving,
                      apiKeyRef: commercialApiKeyInputRef,
                      successMessage: '상용 API 모델을 등록했습니다.',
                    })}
                    className="rounded-2xl border border-border bg-card p-6 shadow-sm space-y-4"
                  >
                    <div className="flex items-center gap-3 border-b border-border pb-4">
                      <div className="rounded-xl bg-blue-100 p-2.5"><Bot className="size-5 text-blue-700" /></div>
                      <div>
                        <h3 className="font-bold text-lg">상용 API 모델 등록</h3>
                        <p className="text-xs text-muted-foreground">OpenAI, Anthropic 등의 API 연동</p>
                      </div>
                    </div>
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <label htmlFor="commercial-provider-name" className="text-sm font-bold text-muted-foreground">등록 이름</label>
                        <input id="commercial-provider-name" value={commercialModelForm.name} onChange={(event) => updateCommercialModelField('name', event.target.value)} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="commercial-provider-type" className="text-sm font-bold text-muted-foreground">제공자</label>
                        <select id="commercial-provider-type" value={commercialModelForm.providerType} onChange={(event) => updateCommercialModelField('providerType', event.target.value)} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary">
                          <option value="openai">OpenAI 호환</option>
                          <option value="anthropic">Anthropic</option>
                          <option value="gemini">Google Gemini</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="commercial-base-url" className="text-sm font-bold text-muted-foreground">API 엔드포인트</label>
                        <input id="commercial-base-url" type="url" value={commercialModelForm.baseUrl} onChange={(event) => updateCommercialModelField('baseUrl', event.target.value)} placeholder="https://api.openai.com/v1" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="grid gap-4 sm:grid-cols-2">
                        <div className="space-y-2">
                          <label htmlFor="commercial-model-id" className="text-sm font-bold text-muted-foreground">모델 식별자</label>
                          <input id="commercial-model-id" value={commercialModelForm.modelIdentifier} onChange={(event) => updateCommercialModelField('modelIdentifier', event.target.value)} placeholder="gpt-4o" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                        </div>
                        <div className="space-y-2">
                          <label htmlFor="commercial-embedding-model" className="text-sm font-bold text-muted-foreground">임베딩 모델</label>
                          <select id="commercial-embedding-model" value={commercialModelForm.embeddingModel} onChange={(event) => updateCommercialModelField('embeddingModel', event.target.value)} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary">
                            {embeddingModelOptions.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="commercial-api-key" className="text-sm font-bold text-muted-foreground">API Key</label>
                        <input id="commercial-api-key" ref={commercialApiKeyInputRef} type="password" onChange={() => setModelProviderStatus(null)} placeholder="저장 시에만 전송" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <button type="submit" disabled={commercialModelSaving || modelProvidersLoading} aria-busy={commercialModelSaving || modelProvidersLoading} className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-bold text-background transition-colors hover:bg-foreground/90 disabled:cursor-not-allowed disabled:opacity-60">
                        {commercialModelSaving ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Plus className="size-4" aria-hidden="true" />}
                        {commercialModelSaving ? '등록 중' : '상용 모델 추가'}
                      </button>
                    </div>
                  </form>

                  <form
                    onSubmit={(event) => createModelProvider(event, localModelForm, {
                      setSaving: setLocalModelSaving,
                      apiKeyRef: localApiKeyInputRef,
                      successMessage: 'Gemma4 로컬 모델을 등록했습니다.',
                    })}
                    className="rounded-2xl border border-border bg-card p-6 shadow-sm space-y-4"
                  >
                    <div className="flex items-center gap-3 border-b border-border pb-4">
                      <div className="rounded-xl bg-emerald-100 p-2.5"><Cpu className="size-5 text-emerald-700" /></div>
                      <div>
                        <h3 className="font-bold text-lg">로컬 모델 등록</h3>
                        <p className="text-xs text-muted-foreground">Ollama, vLLM 등의 자체 호스팅 모델 연동</p>
                      </div>
                    </div>
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <label htmlFor="local-provider-name" className="text-sm font-bold text-muted-foreground">등록 이름</label>
                        <input id="local-provider-name" value={localModelForm.name} onChange={(event) => updateLocalModelField('name', event.target.value)} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="local-base-url" className="text-sm font-bold text-muted-foreground">서버 엔드포인트 URL</label>
                        <input id="local-base-url" type="url" value={localModelForm.baseUrl} onChange={(event) => updateLocalModelField('baseUrl', event.target.value)} placeholder="http://ollama:11434/v1" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="grid gap-4 sm:grid-cols-2">
                        <div className="space-y-2">
                          <label htmlFor="local-model-id" className="text-sm font-bold text-muted-foreground">모델 식별자</label>
                          <input id="local-model-id" value={localModelForm.modelIdentifier} onChange={(event) => updateLocalModelField('modelIdentifier', event.target.value)} placeholder="gemma4:e2b-it-qat" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                        </div>
                        <div className="space-y-2">
                          <label htmlFor="local-embedding-model" className="text-sm font-bold text-muted-foreground">임베딩 모델</label>
                          <select id="local-embedding-model" value={localModelForm.embeddingModel} onChange={(event) => updateLocalModelField('embeddingModel', event.target.value)} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary">
                            {embeddingModelOptions.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="local-api-key" className="text-sm font-bold text-muted-foreground">로컬 API 키 대체값</label>
                        <input id="local-api-key" ref={localApiKeyInputRef} type="password" onChange={() => setModelProviderStatus(null)} placeholder="필요한 경우에만 입력" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <button type="submit" disabled={localModelSaving || modelProvidersLoading} aria-busy={localModelSaving || modelProvidersLoading} className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-lg border border-border bg-background px-4 py-2 text-sm font-bold text-foreground transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-60">
                        {localModelSaving ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Cpu className="size-4" aria-hidden="true" />}
                        {localModelSaving ? '등록 중' : 'Gemma4 로컬 모델 등록'}
                      </button>
                    </div>
                  </form>
                </div>

                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm space-y-4">
                  <div className="flex items-center gap-3 border-b border-border pb-4">
                    <div className="rounded-xl bg-purple-100 p-2.5"><Network className="size-5 text-purple-700" /></div>
                    <div>
                      <h3 className="font-bold text-lg">임베딩 모델 지정</h3>
                      <p className="text-sm text-muted-foreground mt-1">벡터 스토어 및 RAG 구축을 위한 기본 임베딩 모델을 선택합니다.</p>
                    </div>
                  </div>
                  <div className="grid gap-4">
                    <div className="space-y-2">
                      <label htmlFor="embedding-provider" className="text-sm font-bold text-muted-foreground">대상 모델</label>
                      <select
                        id="embedding-provider"
                        value={selectedEmbeddingProvider?.id ?? ''}
                        onChange={(event) => {
                          const providerId = Number.parseInt(event.target.value, 10);
                          const provider = modelProviders.find((candidate) => candidate.id === providerId) ?? null;
                          setSelectedEmbeddingProviderId(Number.isFinite(providerId) ? providerId : null);
                          setSelectedEmbeddingModel(provider?.embedding_model ?? 'embeddinggemma');
                          setModelProviderStatus(null);
                        }}
                        disabled={modelProviders.length === 0}
                        className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {modelProviders.length === 0 ? (
                          <option value="">등록된 모델 없음</option>
                        ) : (
                          modelProviders.map((provider) => (
                            <option key={provider.id} value={provider.id}>{provider.name}</option>
                          ))
                        )}
                      </select>
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                      {embeddingModelOptions.map((option) => (
                        <label key={option.value} className="flex min-h-24 cursor-pointer items-center justify-between rounded-xl border border-border p-4 transition-colors hover:border-primary/50 [&:has(:checked)]:border-primary [&:has(:checked)]:bg-primary/5">
                          <div className="min-w-0">
                            <p className="break-all font-bold">{option.label}</p>
                            <p className="mt-1 text-xs text-muted-foreground">{option.detail}</p>
                          </div>
                          <input
                            type="radio"
                            name="embedding_model"
                            value={option.value}
                            checked={selectedEmbeddingModel === option.value}
                            onChange={() => {
                              setSelectedEmbeddingModel(option.value);
                              setModelProviderStatus(null);
                            }}
                            className="size-4 shrink-0"
                          />
                        </label>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={handleEmbeddingModelSave}
                      disabled={!selectedEmbeddingProvider || embeddingSaving}
                      aria-busy={embeddingSaving}
                      className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-bold text-background transition-colors hover:bg-foreground/90 disabled:cursor-not-allowed disabled:opacity-60 sm:w-fit"
                    >
                      {embeddingSaving ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Network className="size-4" aria-hidden="true" />}
                      {embeddingSaving ? '저장 중' : '임베딩 모델 저장'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {activeTab === '연결 계정' && (
              <div className="space-y-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="font-bold text-xl">메일 및 캘린더 커넥터</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                      회원이 지정한 SMTP/IMAP/POP3/OAuth provider를 사용합니다. Naruon은 메일함 용량이나 SMTP/IMAP 서버를 제공하지 않습니다.
                    </p>
                  </div>
                  <span className="rounded-full border border-border bg-card px-3 py-1 font-mono text-xs font-bold text-foreground">
                    고객 지정 연결
                  </span>
                </div>

                {accountLoading ? (
                  <p className="rounded-xl bg-secondary/60 p-3 text-sm font-semibold text-muted-foreground">계정 설정을 불러오는 중입니다.</p>
                ) : null}
                {accountError ? (
                  <p className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900">{accountError}</p>
                ) : null}
                {accountStatus ? (
                  <p className="rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-sm font-semibold text-emerald-900">{accountStatus}</p>
                ) : null}

                  <div className="grid gap-4 md:grid-cols-2">
                    {accountProtocols.map((protocol) => (
                      <article key={protocol.label} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                      <div className="flex items-start gap-3">
                        <div className="grid size-10 shrink-0 place-items-center rounded-full bg-secondary">
                          <Mail className="size-5 text-primary" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-bold text-base">{protocol.label}</h3>
                            <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${protocol.secretReady ? 'bg-emerald-100 text-emerald-800' : 'bg-secondary text-muted-foreground'}`}>
                              {protocol.secretReady ? '저장된 secret 유지' : 'secret 미설정'}
                            </span>
                          </div>
                          <p className="mt-1 break-all font-mono text-sm text-foreground">{protocol.endpoint}</p>
                          <p className="mt-1 break-all text-sm text-muted-foreground">{protocol.identity}</p>
                          <p className="mt-3 text-sm leading-6 text-muted-foreground">{protocol.detail}</p>
                        </div>
                      </div>
                      </article>
                    ))}
                  </div>

                  <section aria-label="연동 원본 준비도" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-bold text-lg">원본 연결 준비 상태</h3>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">
                          CalDAV/CardDAV/WebDAV 원본 등록과 쓰기 의도 상태를 확인합니다. 이 화면은 외부 저장소 쓰기를 실행하지 않습니다.
                        </p>
                      </div>
                      <span className="rounded-full border border-border bg-background px-3 py-1 font-mono text-xs font-bold text-foreground">
                        OAuth: {oauthConsentState}
                      </span>
                    </div>

                    {sourceReadinessLoading ? (
                      <p className="mt-4 rounded-xl bg-secondary/60 p-3 text-sm font-semibold text-muted-foreground">원본 연결 준비 상태를 불러오는 중입니다.</p>
                    ) : null}
                    {sourceReadinessError ? (
                      <p className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900">{sourceReadinessError}</p>
                    ) : null}

                    {!sourceReadinessLoading && !sourceReadinessError ? (
                      <div className="mt-5 grid gap-4 lg:grid-cols-2">
                        <div className="space-y-3">
                          <div className="flex items-center justify-between gap-3">
                            <h4 className="text-sm font-bold">CalDAV/CardDAV 원본</h4>
                            <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-foreground">{calendarSources.length}개</span>
                          </div>
                          {calendarSources.length > 0 ? (
                            <ul className="divide-y divide-border rounded-xl border border-border bg-background">
                              {calendarSources.map((source, index) => (
                                <li key={source.source_id} className="p-3">
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <p className="text-sm font-bold text-foreground">{`${source.provider} 일정 원본 ${index + 1}`}</p>
                                    <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${source.writeback_enabled ? 'bg-emerald-100 text-emerald-800' : 'bg-secondary text-muted-foreground'}`}>
                                      {getWritebackReadinessLabel(source.writeback_enabled)}
                                    </span>
                                  </div>
                                  <p className="mt-2 text-sm text-foreground">{source.protocol.toUpperCase()} 연결</p>
                                  <p className="mt-1 text-xs text-muted-foreground">{source.capabilities.map(getCapabilityLabel).join(' · ')}</p>
                                  <p className="mt-1 text-xs font-semibold text-muted-foreground">{getEtagReadinessLabel(source.etag)}</p>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="rounded-xl border border-dashed border-border p-3 text-sm font-semibold text-muted-foreground">등록된 CalDAV/CardDAV 원본이 없습니다.</p>
                          )}
                        </div>

                        <div className="space-y-3">
                          <div className="flex items-center justify-between gap-3">
                            <h4 className="text-sm font-bold">WebDAV 저장소</h4>
                            <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-foreground">{webdavAccounts.length}개</span>
                          </div>
                          {webdavAccounts.length > 0 ? (
                            <ul className="divide-y divide-border rounded-xl border border-border bg-background">
                              {webdavAccounts.map((account, index) => (
                                <li key={account.source_id} className="p-3">
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <p className="text-sm font-bold text-foreground">{getWebdavAccountLabel(account, index)}</p>
                                    <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${account.writeback_enabled ? 'bg-emerald-100 text-emerald-800' : 'bg-secondary text-muted-foreground'}`}>
                                      {getWritebackReadinessLabel(account.writeback_enabled)}
                                    </span>
                                  </div>
                                  <p className="mt-2 text-xs font-semibold text-muted-foreground">계정 식별자는 서버 스코프에서만 사용합니다.</p>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="rounded-xl border border-dashed border-border p-3 text-sm font-semibold text-muted-foreground">등록된 WebDAV 저장소가 없습니다.</p>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </section>

                  <form onSubmit={handleAccountSave} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-bold text-lg">Source-backed 계정 설정</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        빈 secret 입력은 기존 저장값을 유지합니다. 실제 연결과 외부 쓰기는 서버 검증과 self-hosted connector 정책을 통과한 뒤 별도 실행됩니다.
                      </p>
                    </div>
                    <button
                      type="submit"
                      disabled={accountSaving || !accountReady}
                      aria-disabled={accountSaving || !accountReady}
                      aria-busy={accountSaving}
                      title={accountSaving ? "저장 중입니다" : !accountReady ? "입력값이 부족합니다" : "계정 설정 저장"}
                      className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-foreground px-5 py-2 text-sm font-bold text-background hover:bg-foreground/90 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {accountSaving && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
                      {accountSaving ? '저장 중' : '계정 설정 저장'}
                    </button>
                  </div>

                  <div className="mt-6 grid gap-5">
                    <section aria-label="SMTP 송신 설정" className="grid gap-3 border-t border-border pt-5 sm:grid-cols-2">
                      <div className="space-y-2">
                        <label htmlFor="smtp-server" className="text-sm font-bold text-muted-foreground">SMTP 서버</label>
                        <input id="smtp-server" name="smtp_server" value={accountForm.smtpServer} onChange={(event) => updateAccountField('smtpServer', event.target.value)} placeholder="smtp.example.com" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="smtp-port" className="text-sm font-bold text-muted-foreground">SMTP 포트</label>
                        <input id="smtp-port" name="smtp_port" type="number" inputMode="numeric" value={accountForm.smtpPort} onChange={(event) => updateAccountField('smtpPort', event.target.value)} placeholder="587" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="smtp-username" className="text-sm font-bold text-muted-foreground">SMTP 사용자</label>
                        <input id="smtp-username" name="smtp_username" value={accountForm.smtpUsername} onChange={(event) => updateAccountField('smtpUsername', event.target.value)} placeholder="sender@example.com" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="smtp-password" className="text-sm font-bold text-muted-foreground">SMTP secret</label>
                        <input id="smtp-password" ref={smtpPasswordInputRef} name="smtp_password" type="password" onChange={() => setAccountStatus(null)} placeholder={accountConfig?.has_smtp_password ? '저장된 secret 유지' : '새 secret 입력'} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                    </section>

                    <section aria-label="IMAP 수신 설정" className="grid gap-3 border-t border-border pt-5 sm:grid-cols-2">
                      <div className="space-y-2">
                        <label htmlFor="imap-server" className="text-sm font-bold text-muted-foreground">IMAP 서버</label>
                        <input id="imap-server" name="imap_server" value={accountForm.imapServer} onChange={(event) => updateAccountField('imapServer', event.target.value)} placeholder="imap.example.com" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="imap-port" className="text-sm font-bold text-muted-foreground">IMAP 포트</label>
                        <input id="imap-port" name="imap_port" type="number" inputMode="numeric" value={accountForm.imapPort} onChange={(event) => updateAccountField('imapPort', event.target.value)} placeholder="993" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="imap-username" className="text-sm font-bold text-muted-foreground">IMAP 사용자</label>
                        <input id="imap-username" name="imap_username" value={accountForm.imapUsername} onChange={(event) => updateAccountField('imapUsername', event.target.value)} placeholder="inbox@example.com" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="imap-password" className="text-sm font-bold text-muted-foreground">IMAP secret</label>
                        <input id="imap-password" ref={imapPasswordInputRef} name="imap_password" type="password" onChange={() => setAccountStatus(null)} placeholder={accountConfig?.has_imap_password ? '저장된 secret 유지' : '새 secret 입력'} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                    </section>

                    <section aria-label="POP3 반입 설정" className="grid gap-3 border-t border-border pt-5 sm:grid-cols-2">
                      <div className="space-y-2">
                        <label htmlFor="pop3-server" className="text-sm font-bold text-muted-foreground">POP3 서버</label>
                        <input id="pop3-server" name="pop3_server" value={accountForm.pop3Server} onChange={(event) => updateAccountField('pop3Server', event.target.value)} placeholder="pop3.example.com" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="pop3-port" className="text-sm font-bold text-muted-foreground">POP3 포트</label>
                        <input id="pop3-port" name="pop3_port" type="number" inputMode="numeric" value={accountForm.pop3Port} onChange={(event) => updateAccountField('pop3Port', event.target.value)} placeholder="995" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="pop3-username" className="text-sm font-bold text-muted-foreground">POP3 사용자</label>
                        <input id="pop3-username" name="pop3_username" value={accountForm.pop3Username} onChange={(event) => updateAccountField('pop3Username', event.target.value)} placeholder="archive@example.com" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="pop3-password" className="text-sm font-bold text-muted-foreground">POP3 secret</label>
                        <input id="pop3-password" ref={pop3PasswordInputRef} name="pop3_password" type="password" onChange={() => setAccountStatus(null)} placeholder={accountConfig?.has_pop3_password ? '저장된 secret 유지' : '새 secret 입력'} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                    </section>

                    <section aria-label="OAuth 앱 설정" className="grid gap-3 border-t border-border pt-5 sm:grid-cols-2">
                      <div className="space-y-2">
                        <label htmlFor="oauth-client-id" className="text-sm font-bold text-muted-foreground">OAuth client ID</label>
                        <input id="oauth-client-id" name="oauth_client_id" value={accountForm.oauthClientId} onChange={(event) => updateAccountField('oauthClientId', event.target.value)} placeholder="client-id" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="oauth-client-secret" className="text-sm font-bold text-muted-foreground">OAuth client secret</label>
                        <input id="oauth-client-secret" ref={oauthClientSecretInputRef} name="oauth_client_secret" type="password" onChange={() => setAccountStatus(null)} placeholder={accountConfig?.has_oauth_client_secret ? '저장된 secret 유지' : '새 secret 입력'} className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                      <div className="space-y-2 sm:col-span-2">
                        <label htmlFor="oauth-redirect-uri" className="text-sm font-bold text-muted-foreground">OAuth redirect URI</label>
                        <input id="oauth-redirect-uri" name="oauth_redirect_uri" value={accountForm.oauthRedirectUri} onChange={(event) => updateAccountField('oauthRedirectUri', event.target.value)} placeholder="https://naruon.net/oauth/mail/callback" className="w-full rounded-lg border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
                      </div>
                    </section>
                  </div>
                </form>
              </div>
            )}

            {activeTab === '개발자' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-bold text-xl">개발자 및 시스템 (Observability)</h2>
                    <p className="text-sm text-muted-foreground mt-1">Naruon 인프라 모니터링, 추적 및 보안 로그에 접근합니다.</p>
                  </div>
                </div>

                <section aria-label="Self-hosted connector manifest" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-bold text-lg">Self-hosted connector 등록 상태</h3>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        Naruon은 메일 서버가 아닙니다. 고객망의 self-hosted connector가 outbound-only로 naruon.net control plane에 연결해 IMAP/SMTP/CalDAV/WebDAV 접근을 중계합니다.
                      </p>
                    </div>
                    {connectorManifest ? (
                      <span className="rounded-full border border-border bg-background px-3 py-1 font-mono text-xs font-bold text-foreground">
                        Self-hosted connector
                      </span>
                    ) : null}
                  </div>

                  {runnerLoading ? (
                    <p className="mt-4 rounded-xl bg-secondary/60 p-3 text-sm font-semibold text-muted-foreground">connector manifest를 불러오는 중입니다.</p>
                  ) : null}
                  {runnerError ? (
                    <p className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900">{runnerError}</p>
                  ) : null}
                  <div className="mt-5 grid gap-3 border-t border-border pt-4 sm:grid-cols-[minmax(0,1fr)_auto]">
                    <dl className="grid gap-3 sm:grid-cols-3">
                      <div>
                        <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">워크스페이스 등록</dt>
                        <dd className="mt-1 text-sm font-bold text-foreground">{runnerConfig?.workspace_id ? '서버 스코프 확인됨' : '미확인'}</dd>
                      </div>
                      <div>
                        <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">등록 상태</dt>
                        <dd className="mt-1 text-sm font-bold text-foreground">{getRegistrationLabel(runnerConfig?.configured)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">등록 지문</dt>
                        <dd className="mt-1 break-all font-mono text-sm text-foreground">{runnerConfig?.fingerprint ?? '기록 없음'}</dd>
                      </div>
                    </dl>
                    <button
                      type="button"
                      onClick={handleRunnerTokenRotate}
                      disabled={runnerRotating}
                      aria-disabled={runnerRotating}
                      aria-busy={runnerRotating}
                      title={runnerRotating ? "등록 토큰을 회전 중입니다" : "등록 토큰을 회전합니다"}
                      className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-bold text-background hover:bg-foreground/90 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <RefreshCw className={`size-4 ${runnerRotating ? 'animate-spin' : ''}`} />
                      {runnerRotating ? '회전 중' : '등록 토큰 회전'}
                    </button>
                  </div>
                  {runnerRotateError ? (
                    <p className="mt-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900">{runnerRotateError}</p>
                  ) : null}
                  {runnerTokenIssued ? (
                    <div className="mt-3 rounded-xl border border-emerald-300 bg-emerald-50 p-3">
                      <p className="text-sm font-bold text-emerald-900">등록 토큰이 생성되었습니다.</p>
                      <p className="mt-2 text-sm leading-6 text-emerald-950">원문 토큰은 화면에 보관하지 않습니다. 운영자가 승인된 보안 채널에서만 수령해야 합니다.</p>
                    </div>
                  ) : null}
                  {connectorManifest ? (
                    <div className="mt-5 space-y-4">
                      <dl className="grid gap-3 border-t border-border pt-4 sm:grid-cols-3">
                        <div>
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">네트워크 방식</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{getNetworkModeLabel(connectorManifest.network_mode)}</dd>
                        </div>
                        <div>
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">제어 평면</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{connectorManifest.control_plane_domain ? '등록됨' : '미설정'}</dd>
                        </div>
                        <div>
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">사용 범위</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{getRunnerUsageLabel(connectorManifest.runner_usage)}</dd>
                        </div>
                      </dl>

                      <div className="grid gap-4 border-t border-border pt-4 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">로컬 프로토콜</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {connectorManifest.local_protocols.map((protocol) => (
                              <span key={protocol} className="rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-foreground">{protocol.toUpperCase()}</span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">금지 역할</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {connectorManifest.prohibited_roles.map((role) => (
                              <span key={role} className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-700">{getProhibitedRoleLabel(role)}</span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </section>

                <section aria-label="Open-source APM operational signals" className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="flex items-center gap-2 font-bold text-lg">
                        <Activity className="size-5 text-teal-600" />
                        Connector 상태와 APM 신호
                      </h3>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        서버가 확인한 self-hosted connector 연결, OpenTelemetry, Prometheus 상태만 표시합니다. 외부 쓰기 실행은 여기서 수행하지 않습니다.
                      </p>
                    </div>
                    {operationalSignals ? (
                      <span className="rounded-full border border-border bg-background px-3 py-1 font-mono text-xs font-bold text-foreground">
                        감사 근거 기록됨
                      </span>
                    ) : null}
                  </div>

                  {operationalLoading ? (
                    <p className="mt-4 rounded-xl bg-secondary/60 p-3 text-sm font-semibold text-muted-foreground">운영 신호를 불러오는 중입니다.</p>
                  ) : null}
                  {operationalError ? (
                    <p className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900">{operationalError}</p>
                  ) : null}
                  {operationalSignals ? (
                    <div className="mt-5 space-y-5">
                      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                        <div className="rounded-xl border border-border bg-background p-3">
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">연결 상태</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{getConnectorStateLabel(operationalSignals.connector.connection_state)}</dd>
                        </div>
                        <div className="rounded-xl border border-border bg-background p-3">
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">활성 연결</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{operationalSignals.connector.active_connection_count}개</dd>
                        </div>
                        <div className="rounded-xl border border-border bg-background p-3">
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">prometheus</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{operationalSignals.telemetry.prometheus_metrics_enabled ? '활성' : '미설정'}</dd>
                        </div>
                        <div className="rounded-xl border border-border bg-background p-3">
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">OTel traces</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{operationalSignals.telemetry.otel_traces_enabled ? '활성' : '미설정'}</dd>
                        </div>
                        <div className="rounded-xl border border-border bg-background p-3">
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">writeback queue</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{getQueueDepthLabel(operationalSignals.connector.queue_depth_state)}</dd>
                          <dd className="mt-2 space-y-1 text-xs font-semibold text-muted-foreground">
                            <span className="block">재시도 대기 {operationalSignals.connector.queue_depth.pending_count}건</span>
                            <span className="block">진행 {operationalSignals.connector.queue_depth.running_count}건 · 실패 {operationalSignals.connector.queue_depth.failed_count}건</span>
                          </dd>
                        </div>
                      </dl>

                      <dl className="grid gap-3 border-t border-border pt-4 sm:grid-cols-3">
                        <div>
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">최근 하트비트</dt>
                          <dd className="mt-1 font-mono text-sm text-foreground">{operationalSignals.connector.last_heartbeat_at ?? '기록 없음'}</dd>
                        </div>
                        <div>
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">최근 연결 종료</dt>
                          <dd className="mt-1 font-mono text-sm text-foreground">{operationalSignals.connector.last_disconnect_at ?? '기록 없음'}</dd>
                        </div>
                        <div>
                          <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">OTel endpoint</dt>
                          <dd className="mt-1 text-sm font-bold text-foreground">{operationalSignals.telemetry.otel_endpoint_host ? '설정됨' : '미설정'}</dd>
                        </div>
                      </dl>

                      <div aria-labelledby="recent-connector-signals-heading" className="border-t border-border pt-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h4 id="recent-connector-signals-heading" className="font-bold text-sm">최근 connector 신호</h4>
                          <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-foreground">{connectorEvents.length}건</span>
                        </div>
                        {connectorEvents.length > 0 ? (
                          <ol className="mt-3 divide-y divide-border">
                            {connectorEvents.map((event) => (
                              <li key={event.event_uid} className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                                <div className="min-w-0">
                                  <p className="text-sm font-bold text-foreground">{getConnectorStateLabel(event.state_code)}</p>
                                  <p className="mt-1 break-words text-sm leading-6 text-muted-foreground">{getConnectorEventDetail(event)}</p>
                                  <p className="mt-1 text-xs font-semibold text-muted-foreground">근거: 서버 관측 이벤트</p>
                                </div>
                                <time className="break-all font-mono text-xs text-muted-foreground sm:text-right">{event.observed_at}</time>
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p className="mt-3 text-sm leading-6 text-muted-foreground">아직 저장된 runner 이벤트가 없습니다.</p>
                        )}
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        {operationalSignals.signals.map((signal) => (
                          <article key={signal.signal_key} className="rounded-xl border border-border bg-background p-4">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <h4 className="font-bold text-sm">{signal.display_name}</h4>
                              <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-foreground">{getConnectorStateLabel(signal.state)}</span>
                            </div>
                            <p className="mt-2 text-sm leading-6 text-muted-foreground">{getOperationalSignalDetail(signal)}</p>
                            <p className="mt-3 text-xs font-semibold text-muted-foreground">근거: {getOperationalEvidenceLabel(signal.evidence_source)}</p>
                          </article>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>

                <section aria-label="OIDC 인증 세션" className="mt-6 rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Shield className="size-5 text-blue-500" />
                        <h3 className="font-bold text-lg">OIDC 인증 세션</h3>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        Keycloak/Casdoor OIDC 토큰을 브라우저 bearer 세션으로 연결합니다.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={handleOidcLogin}
                        disabled={!oidcBrowserConfig}
                        title={!oidcBrowserConfig ? "OIDC 브라우저 설정이 없습니다" : "OIDC 로그인"}
                        className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        OIDC 로그인
                      </button>
                      <button
                        type="button"
                        onClick={handleOidcLogout}
                        disabled={!oidcSessionClaims.userId}
                        title={!oidcSessionClaims.userId ? "로그인된 세션이 없습니다" : "로그아웃"}
                        className="rounded-lg border border-border px-4 py-2 text-sm font-bold text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        로그아웃
                      </button>
                    </div>
                  </div>
                  {oidcActionError ? (
                    <p role="alert" className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700">{oidcActionError}</p>
                  ) : null}
                  <dl className="mt-5 grid gap-3 md:grid-cols-3">
                    <div className="rounded-xl border border-border bg-background p-3">
                      <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Issuer</dt>
                      <dd className="mt-1 text-sm font-semibold text-foreground">{oidcBrowserConfig?.issuerUrl ? '설정됨' : '미설정'}</dd>
                    </div>
                    <div className="rounded-xl border border-border bg-background p-3">
                      <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Client</dt>
                      <dd className="mt-1 text-sm font-semibold text-foreground">{oidcBrowserConfig?.clientId ? '등록됨' : '미설정'}</dd>
                    </div>
                    <div className="rounded-xl border border-border bg-background p-3">
                      <dt className="text-xs font-bold uppercase tracking-wide text-muted-foreground">세션</dt>
                      <dd className="mt-1 text-sm font-semibold text-foreground">
                        {oidcSessionClaims.userId
                          ? `서명된 세션 연결됨 · ${oidcSessionClaims.organizationId ? '조직 스코프' : '개인 스코프'}`
                          : '서명된 세션 없음'}
                      </dd>
                    </div>
                  </dl>
                </section>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
                  <a href="http://localhost:3000" target="_blank" rel="noopener noreferrer" className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-6 shadow-sm hover:border-primary/50 transition-colors">
                    <Monitor className="size-8 text-orange-500 mb-2" />
                    <h3 className="font-bold text-lg">Grafana 대시보드</h3>
                    <p className="text-sm text-muted-foreground">OpenTelemetry 기반의 APM, 트래픽 메트릭 및 시스템 자원 모니터링을 확인합니다.</p>
                  </a>
                  <a href="http://localhost:8080" target="_blank" rel="noopener noreferrer" className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-6 shadow-sm hover:border-primary/50 transition-colors">
                    <Shield className="size-8 text-blue-500 mb-2" />
                    <h3 className="font-bold text-lg">Keycloak 관리 콘솔</h3>
                    <p className="text-sm text-muted-foreground">OIDC 프로바이더, SSO 인증, 역할 기반 접근 제어(RBAC)를 구성합니다.</p>
                  </a>
                  <a href="http://localhost:3100" target="_blank" rel="noopener noreferrer" className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-6 shadow-sm hover:border-primary/50 transition-colors">
                    <AlertCircle className="size-8 text-slate-500 mb-2" />
                    <h3 className="font-bold text-lg">Loki 로그 서버</h3>
                    <p className="text-sm text-muted-foreground">분산 아키텍처 환경의 컨테이너 로그 및 어플리케이션 에러 로그를 검색합니다.</p>
                  </a>
                  <a href="http://localhost:3200" target="_blank" rel="noopener noreferrer" className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-6 shadow-sm hover:border-primary/50 transition-colors">
                    <RefreshCw className="size-8 text-teal-500 mb-2" />
                    <h3 className="font-bold text-lg">Tempo 분산 추적</h3>
                    <p className="text-sm text-muted-foreground">FastAPI의 엔드포인트 지연율 및 MSA 구성요소 간의 호출 트레이스를 시각화합니다.</p>
                  </a>
                </div>
              </div>
            )}

            {detailSurface ? (
              <section aria-label={`${activeTab} 상세 설정`} className="space-y-5">
                <div>
                  <h2 className="font-bold text-xl">{detailSurface.heading}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">{detailSurface.copy}</p>
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  {detailSurface.items.map((item) => (
                    <article key={item.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                      <p className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary inline-flex">{item.status}</p>
                      <h3 className="mt-4 font-bold text-base">{item.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</p>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
            
          </div>
        </main>
      </div>
    </div>
  );
}
