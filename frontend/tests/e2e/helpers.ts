import type { Page, Request, Route } from '@playwright/test';

const email = {
  id: 7,
  message_id: '<q2@example.com>',
  source_message_id: '<q2@example.com>',
  thread_id: 'thread-q2',
  sender: '김지현 PM',
  recipients: 'user@naruon.ai',
  reply_to: 'jihyun@naruon.ai',
  subject: 'Q2 출시 계획 및 우선순위 조정',
  date: '2026-05-11T09:30:00Z',
  body: 'Q2 출시 일정과 마케팅 계획을 우선순위 기준으로 재정렬해 보았습니다.',
  snippet: 'Q2 출시 계획과 우선순위 조정 요청입니다.',
  unread: true,
  reply_count: 2,
  score: 0.91,
};

const sibling = {
  ...email,
  id: 8,
  message_id: '<q2-reply@example.com>',
  body: '파트너 미팅 전까지 일정 확인이 필요합니다.',
};

const sentEmail = {
  ...email,
  id: 31,
  message_id: '<sent-q2@example.com>',
  thread_id: 'thread-sent-q2',
  sender: 'Seongho <user@naruon.ai>',
  recipients: 'partner@example.com',
  subject: '벤더 계약 답변 요청',
  date: '2026-05-11T12:30:00Z',
  snippet: 'Please reply when the vendor contract review is ready.',
  unread: false,
  reply_count: 1,
  requires_reply: true,
  is_self_sent: false,
};

const selfSentNote = {
  ...email,
  id: 32,
  message_id: '<self-note@example.com>',
  thread_id: 'thread-self-note',
  sender: 'user@naruon.ai',
  recipients: 'user@naruon.ai',
  subject: '나에게 보낸 지식 메모',
  date: '2026-05-11T13:10:00Z',
  snippet: '다음 분기 전략 회의 전에 지식으로 정리할 메모입니다.',
  unread: false,
  reply_count: 1,
  requires_reply: false,
  is_self_sent: true,
};

const sentFollowUp = {
  ...email,
  id: 33,
  message_id: '<sent-follow-up@example.com>',
  thread_id: 'thread-sent-follow-up',
  sender: 'Seongho <user@naruon.ai>',
  recipients: 'finance@example.com',
  subject: '예산 승인 후속 확인',
  date: '2026-05-11T14:20:00Z',
  snippet: 'Can you confirm whether the budget approval is ready?',
  unread: false,
  reply_count: 1,
  requires_reply: true,
  is_self_sent: false,
};

const sentResolved = {
  ...email,
  id: 34,
  message_id: '<sent-resolved@example.com>',
  thread_id: 'thread-sent-resolved',
  sender: 'Seongho <user@naruon.ai>',
  recipients: 'ops@example.com',
  subject: '운영 점검 회신 완료',
  date: '2026-05-11T15:00:00Z',
  snippet: '운영 점검 후속 메일이며 이미 회신이 연결된 스레드입니다.',
  unread: false,
  reply_count: 2,
  requires_reply: false,
  is_self_sent: false,
};

const sentKnowledge = {
  ...email,
  id: 35,
  message_id: '<sent-knowledge@example.com>',
  thread_id: 'thread-sent-knowledge',
  sender: 'user@naruon.ai',
  recipients: 'user@naruon.ai',
  subject: '고객 미팅 지식 정리',
  date: '2026-05-11T16:00:00Z',
  snippet: '고객 미팅에서 나온 판단 포인트를 지식으로 정리합니다.',
  unread: false,
  reply_count: 1,
  requires_reply: false,
  is_self_sent: true,
};

const mobileAttachmentResult = {
  ...email,
  id: 17,
  subject: '브랜드 에셋 검토 자료',
  sender: '박서연 디자이너',
  date: '2026-05-11T10:15:00Z',
  snippet: '모바일 워크스페이스에 필요한 브랜드 에셋과 첨부 자료입니다.',
};

const mobilePeopleResult = {
  ...email,
  id: 18,
  subject: '강민수 의사결정 메모',
  sender: '강민수 리드',
  date: '2026-05-11T11:00:00Z',
  snippet: '일정과 사람 맥락을 함께 확인해야 하는 의사결정 메모입니다.',
};

const calendarCandidate = {
  ...email,
  id: 27,
  subject: '파트너 미팅 일정 확정',
  sender: '이지은 파트너',
  date: '2026-05-12T13:00:00Z',
  snippet: '파트너 미팅 일정을 확정하고 캘린더에 반영해야 합니다.',
};

const aiHubPrompts = [
  { id: 101, title: '의사결정 로그 맥락 종합', description: '출시 일정과 파트너 리스크를 함께 검토합니다.' },
  { id: 102, title: '계약 리스크 점검', description: '계약서, 첨부, 메일 스레드를 판단 포인트로 정리합니다.' },
  { id: 103, title: '후속 실행 항목', description: '답장, 일정, 할 일을 담당자별 실행 흐름으로 나눕니다.' },
];

const aiHubSurface = {
  summary_cards: [
    {
      summary_key: 'prompt_templates',
      label_text: '프롬프트',
      value_text: '3',
      detail_text: 'source-backed templates',
      state_code: 'ready',
    },
    {
      summary_key: 'workflow_blueprints',
      label_text: '워크플로우',
      value_text: '1',
      detail_text: 'source-backed execution flows',
      state_code: 'ready',
    },
    {
      summary_key: 'ai_providers',
      label_text: '판단 보조',
      value_text: '1/1',
      detail_text: 'active organization providers',
      state_code: 'ready',
    },
    {
      summary_key: 'evaluation_readiness',
      label_text: '평가',
      value_text: '85%',
      detail_text: 'derived operational readiness',
      state_code: 'ready',
    },
    {
      summary_key: 'run_events',
      label_text: '실행 이력',
      value_text: '1',
      detail_text: 'scoped execution evidence',
      state_code: 'ready',
    },
  ],
  prompt_cards: aiHubPrompts.map((prompt) => ({
    prompt_key: `prompt_${prompt.id}`,
    prompt_title: prompt.title,
    description_text: prompt.description,
    shared_scope: prompt.id === 102,
    owner_label: prompt.id === 102 ? 'shared-template' : 'admin',
    updated_at: '2026-05-29T09:30:00Z',
  })),
  workflow_cards: [
    {
      workflow_key: 'workflow_decision_log',
      workflow_title: '의사결정 로그 자동 작성',
      trigger_source: 'workflow_definition',
      state_code: 'ready',
      evidence_text: '2 persisted workflow steps',
    },
  ],
  agent_cards: [
    {
      agent_key: 'agent_primary',
      agent_title: 'Primary OpenAI',
      model_label: 'openai',
      state_code: 'active',
      configured: true,
      governance_text: 'organization llm provider registry',
    },
  ],
  evaluation_metrics: [
    {
      metric_key: 'provider_readiness',
      metric_label: 'Provider 준비도',
      score_value: 100,
      trend_text: '1/1 active providers',
    },
    {
      metric_key: 'execution_readiness',
      metric_label: '실행 준비도',
      score_value: 85,
      trend_text: 'derived from provider, prompt, and audit evidence',
    },
  ],
  run_events: [
    {
      event_key: 'agent_run_decision_log',
      event_title: '워크플로우 실행',
      state_code: 'completed',
      evidence_source: 'agent_run_records',
      observed_at: '2026-05-29T09:30:00Z',
      detail_text: '3개 판단 포인트를 추출했습니다.',
    },
  ],
};

const runnerConfig = {
  workspace_id: 'workspace-org-acme',
  configured: true,
  fingerprint: '***abc12345',
  updated_at: '2026-05-27T06:00:00Z',
  connector_manifest: {
    role: 'self-hosted_connector',
    network_mode: 'outbound_only',
    control_plane_domain: 'naruon.net',
    local_protocols: ['imap', 'pop3', 'smtp', 'caldav', 'carddav', 'webdav'],
    prohibited_roles: ['smtp_server', 'imap_server', 'mx_host'],
    runner_usage: 'ci_smoke_only',
  },
};

const operationalSignals = {
  workspace_id: 'workspace-org-acme',
  audit_event: 'observability.operational_signals.viewed',
  telemetry: {
    prometheus_metrics_enabled: true,
    otel_traces_enabled: true,
    otel_endpoint_configured: true,
    otel_endpoint_host: 'otel-collector:4317',
  },
  connector: {
    workspace_id: 'workspace-org-acme',
    registration_state: 'registration_configured',
    connection_state: 'connected',
    active_connection_count: 1,
    control_plane_domain: 'naruon.net',
    network_mode: 'outbound_only',
    runner_usage: 'ci_smoke_only',
    local_protocols: ['imap', 'pop3', 'smtp', 'caldav', 'carddav', 'webdav'],
    last_heartbeat_at: '2026-05-27T12:00:00Z',
    last_disconnect_at: null,
    queue_depth_state: 'degraded',
    queue_depth: {
      pending_count: 2,
      running_count: 1,
      failed_count: 1,
      total_count: 4,
      next_retry_at: '2026-06-15T12:05:00Z',
    },
    recent_events: [
      {
        event_uid: 'connector_evt_heartbeat',
        signal_key: 'connector_heartbeat',
        state_code: 'heartbeat',
        detail_text: 'outbound runner heartbeat received',
        observed_at: '2026-05-27T12:00:00Z',
      },
      {
        event_uid: 'connector_evt_connected',
        signal_key: 'connector_heartbeat',
        state_code: 'connected',
        detail_text: 'outbound runner socket connected',
        observed_at: '2026-05-27T11:59:00Z',
      },
    ],
  },
  signals: [
    {
      signal_key: 'connector_heartbeat',
      display_name: 'Connector heartbeat',
      state: 'enabled',
      evidence_source: 'runner WebSocket manager',
      detail: 'Live heartbeat uses active outbound runner sockets.',
      provider_write_executed: false,
    },
    {
      signal_key: 'writeback_retry_queue',
      display_name: 'Writeback retry queue',
      state: 'enabled',
      evidence_source: 'provider_writeback_retry_items',
      detail: '4 queued writeback retry items are tracked by state.',
      provider_write_executed: false,
    },
    {
      signal_key: 'sync_lag',
      display_name: 'Sync lag',
      state: 'instrumentation_pending',
      evidence_source: 'provider adapters',
      detail: 'Provider sync lag will be emitted by source-backed connector jobs.',
      provider_write_executed: false,
    },
    {
      signal_key: 'writeback_conflicts',
      display_name: 'Writeback conflicts',
      state: 'intent_only',
      evidence_source: 'calendar and WebDAV writeback-intent APIs',
      detail: 'Conflict handling is surfaced at intent boundaries.',
      provider_write_executed: false,
    },
  ],
};

const securityAccessSurface = {
  scope_kind: 'organization',
  viewer: {
    role: 'tenant_admin',
    scope_kind: 'organization',
  },
  sources: [
    {
      source_type: 'webdav_repository',
      source_label: 'WebDAV repository',
      scope_kind: 'organization',
      capabilities: ['read', 'write', 'etag'],
      writeback_enabled: true,
      policy_decision: {
        resource_label: 'WebDAV repository',
        resource_type: 'webdav_repository',
        allowed: true,
        reason: 'allowed',
        evidence_label: 'webdav_source_evidence',
      },
      last_observed_at: '2026-05-28T04:00:00Z',
    },
    {
      source_type: 'caldav_source',
      source_label: 'Customer CalDAV',
      scope_kind: 'organization',
      capabilities: ['read', 'write', 'etag'],
      writeback_enabled: true,
      policy_decision: {
        resource_label: 'Customer CalDAV source',
        resource_type: 'caldav_source',
        allowed: true,
        reason: 'allowed',
        evidence_label: 'calendar_source_evidence',
      },
      last_observed_at: '2026-05-28T04:00:00Z',
    },
  ],
  connector_events: [
    {
      state_code: 'heartbeat',
      evidence_label: 'connector_observation_evidence',
      observed_at: '2026-05-28T04:00:00Z',
    },
  ],
  durable_audit_events: [
    {
      actor_role: 'tenant_admin',
      scope_kind: 'organization',
      event_action: 'update',
      resource_type: 'llm_provider',
      evidence_label: 'server_audit_evidence',
      observed_at: '2026-05-28T04:02:00Z',
    },
  ],
  policy_decisions: [
    {
      resource_label: 'WebDAV repository',
      resource_type: 'webdav_repository',
      allowed: true,
      reason: 'allowed',
      evidence_label: 'webdav_source_evidence',
    },
    {
      resource_label: 'Cross-organization provider secret',
      resource_type: 'provider_secret',
      allowed: false,
      reason: 'organization_denied',
      evidence_label: 'policy_engine_evidence',
    },
    {
      resource_label: 'Regional export outside policy',
      resource_type: 'data_export',
      allowed: false,
      reason: 'data_region_denied',
      evidence_label: 'policy_engine_evidence',
    },
  ],
  external_share_reviews: [
    {
      source_type: 'webdav_repository',
      review_label: 'WebDAV repository writeback boundary',
      exposure_level: 'external_writeback',
      decision_reason: 'allowed',
    },
    {
      source_type: 'caldav_source',
      review_label: 'Customer CalDAV writeback boundary',
      exposure_level: 'external_writeback',
      decision_reason: 'allowed',
    },
  ],
  policy_order: [
    {
      display_name: 'Signed session identity',
      evidence_label: 'signed_session_evidence',
    },
    {
      display_name: 'Organization and workspace scope',
      evidence_label: 'signed_session_evidence',
    },
    {
      display_name: 'Data-region deny',
      evidence_label: 'policy_engine_evidence',
    },
    {
      display_name: 'RBAC allow after ABAC denies',
      evidence_label: 'policy_engine_evidence',
    },
  ],
};

const dataQualitySurface = {
  workspace_id: 'workspace-org-acme',
  organization_id: 'org-acme',
  audit_event: 'data.quality_surface.viewed',
  provider_write_executed: false,
	  repositories: [
    {
      source_id: 'email_repository',
      repository_type: 'email_repository',
      display_name: 'Scoped email archive',
      object_count: 4,
      writeback_enabled: null,
      evidence_source: 'emails',
      provider_write_executed: false,
    },
    {
      source_id: 'attachment_repository',
      repository_type: 'attachment_repository',
      display_name: 'Scoped attachment archive',
      object_count: 3,
      writeback_enabled: null,
      evidence_source: 'attachments',
      provider_write_executed: false,
    },
    {
      source_id: 'document_repository',
      repository_type: 'document_repository',
      display_name: 'Scoped document repository',
      object_count: 1,
      writeback_enabled: null,
      evidence_source: 'documents',
      provider_write_executed: false,
    },
    {
      source_id: 'webdav_src_primary',
      repository_type: 'webdav_account',
      display_name: 'Customer WebDAV account',
      object_count: 0,
      writeback_enabled: true,
      evidence_source: 'webdav_accounts',
      provider_write_executed: false,
    },
    {
      source_id: 'webdav_folder_roadmap',
      repository_type: 'project_folder',
      display_name: 'Naruon Roadmap 2026',
      object_count: 0,
      writeback_enabled: null,
      evidence_source: 'project_folders',
      provider_write_executed: false,
	    },
	  ],
	  repository_assets: [
	    {
	      asset_key: 'doc_repository_ready',
	      asset_type: 'workspace_document',
	      display_name: 'roadmap.md',
	      source_label: 'Workspace document',
	      state_code: 'ready',
	      detail_text: 'document status: uploaded',
	      content_chars: 128,
	      captured_at: '2026-05-28T05:46:00Z',
	      evidence_source: 'documents.document_status',
	      thread_key: 'workspace_document',
	      provider_write_executed: false,
	    },
	    {
	      asset_key: 'asset_repository_ready',
	      asset_type: 'email_attachment',
	      display_name: 'roadmap.pdf',
	      source_label: 'Q2 roadmap source email',
	      state_code: 'ready',
	      detail_text: 'content and thread evidence ready',
	      content_chars: 4096,
	      captured_at: '2026-05-28T05:45:00Z',
	      evidence_source: 'attachments.content, emails.thread_id',
	      thread_key: 'thread_repository_ready',
	      provider_write_executed: false,
	    },
	    {
	      asset_key: 'asset_repository_pending',
	      asset_type: 'email_attachment',
	      display_name: 'blank-notes.md',
	      source_label: 'Forwarded duplicate source email',
	      state_code: 'needs_attention',
	      detail_text: 'content extraction pending, canonical thread pending',
	      content_chars: 0,
	      captured_at: '2026-05-28T05:43:00Z',
	      evidence_source: 'attachments.content, emails.thread_id',
	      thread_key: 'thread_missing',
	      provider_write_executed: false,
	    },
	  ],
	  pipeline_stages: [
    {
      stage_key: 'source_registry',
      display_name: 'Source registry',
      status_code: 'ready',
      progress_percent: 100,
      evidence_source: 'webdav_accounts, project_folders',
      detail_text: '2 customer-owned sources are in scope.',
      provider_write_executed: false,
    },
    {
      stage_key: 'ingestion_inventory',
      display_name: 'Ingestion inventory',
      status_code: 'ready',
      progress_percent: 100,
      evidence_source: 'emails, attachments',
      detail_text: '4 emails and 3 attachments are visible in the signed workspace scope.',
      provider_write_executed: false,
    },
    {
      stage_key: 'canonical_threading',
      display_name: 'Canonical threading',
      status_code: 'needs_attention',
      progress_percent: 75,
      evidence_source: 'emails.thread_id',
      detail_text: '1 emails need canonical thread ids.',
      provider_write_executed: false,
    },
    {
      stage_key: 'embedding_inventory',
      display_name: 'Embedding inventory',
      status_code: 'running',
      progress_percent: 57,
      evidence_source: 'emails.embedding, attachments.embedding',
      detail_text: '4 of 7 objects have vectors.',
      provider_write_executed: false,
    },
    {
      stage_key: 'connector_observability',
      display_name: 'Connector observability',
      status_code: 'ready',
      progress_percent: 100,
      evidence_source: 'connector_signal_events',
      detail_text: '1 connector events are in scope.',
      provider_write_executed: false,
    },
  ],
  embedding_collections: [
    {
      collection_key: 'emails_embedding',
      display_name: 'Email vectors',
      object_count: 4,
      embedded_count: 3,
      embedding_model: 'text-embedding-3-small',
      vector_dimensions: 1536,
      status_code: 'running',
      evidence_source: 'emails.embedding',
      provider_write_executed: false,
    },
    {
      collection_key: 'attachments_embedding',
      display_name: 'Attachment vectors',
      object_count: 3,
      embedded_count: 1,
      embedding_model: 'text-embedding-3-small',
      vector_dimensions: 1536,
      status_code: 'running',
      evidence_source: 'attachments.embedding',
      provider_write_executed: false,
    },
  ],
  quality_checks: [
    {
      check_key: 'thread_id_integrity',
      display_name: 'Thread id integrity',
      status_code: 'needs_attention',
      issue_count: 1,
      total_count: 4,
      evidence_source: 'emails.thread_id',
      detail_text: 'Some scoped emails need canonical thread ids.',
      provider_write_executed: false,
    },
    {
      check_key: 'dedupe_fingerprint',
      display_name: 'Dedupe fingerprint',
      status_code: 'needs_attention',
      issue_count: 2,
      total_count: 4,
      evidence_source: 'emails.fingerprint',
      detail_text: 'Some scoped emails need duplicate-detection fingerprints.',
      provider_write_executed: false,
    },
    {
      check_key: 'attachment_content',
      display_name: 'Attachment content',
      status_code: 'needs_attention',
      issue_count: 1,
      total_count: 3,
      evidence_source: 'attachments.content',
      detail_text: 'Some scoped attachments need extracted content.',
      provider_write_executed: false,
    },
    {
      check_key: 'content_segment_text_readiness',
      display_name: 'Content segment text readiness',
      status_code: 'needs_attention',
      issue_count: 1,
      total_count: 8,
      evidence_source: 'content_segments.word_count, content_segments.safe_text_content',
      detail_text: 'Some DOM paragraph segments need non-empty safe text and word counts.',
      provider_write_executed: false,
    },
    {
      check_key: 'knowledge_graph_evidence_endpoint_readiness',
      display_name: 'Knowledge graph evidence endpoints',
      status_code: 'needs_attention',
      issue_count: 2,
      total_count: 10,
      evidence_source: 'knowledge_graph_edges.source_segment_id, knowledge_graph_edges.target_segment_id',
      detail_text: 'Some knowledge graph edges need paragraph segment evidence endpoints.',
      provider_write_executed: false,
    },
    {
      check_key: 'connector_signal',
      display_name: 'Connector signal coverage',
      status_code: 'pass',
      issue_count: 0,
      total_count: 1,
      evidence_source: 'connector_signal_events',
      detail_text: 'Connector evidence is visible for this workspace.',
      provider_write_executed: false,
    },
  ],
  attachment_parse_breakdown: [
    {
      content_type: 'application/octet-stream',
      parse_content_type: 'text/markdown',
      parse_status: 'parsed',
      parser_key: 'markdown',
      display_name: 'Markdown attachments',
      object_count: 2,
      evidence_source: 'email_attachments.content_type, email_attachments.parse_content_type, email_attachments.parse_status, email_attachments.parser_key',
      provider_write_executed: false,
    },
    {
      content_type: 'application/pdf',
      parse_content_type: 'application/pdf',
      parse_status: 'unsupported_content_type',
      parser_key: 'unsupported_binary',
      display_name: 'Unsupported binary attachments',
      object_count: 1,
      evidence_source: 'email_attachments.content_type, email_attachments.parse_content_type, email_attachments.parse_status, email_attachments.parser_key',
      provider_write_executed: false,
    },
  ],
  content_graph_breakdown: [
    {
      source_kind: 'email_body',
      segment_kind: 'paragraph',
      object_count: 6,
      evidence_source: 'content_segments.source_kind, content_segments.segment_kind',
      provider_write_executed: false,
    },
    {
      source_kind: 'attachment',
      segment_kind: 'heading',
      object_count: 2,
      evidence_source: 'content_segments.source_kind, content_segments.segment_kind',
      provider_write_executed: false,
    },
  ],
  knowledge_graph_breakdown: [
    {
      source_kind: 'email_body',
      edge_kind: 'node_has_segment',
      object_count: 8,
      evidence_source: 'knowledge_graph_edges.source_kind, knowledge_graph_edges.edge_kind',
      provider_write_executed: false,
    },
    {
      source_kind: 'attachment',
      edge_kind: 'heading_contains_segment',
      object_count: 2,
      evidence_source: 'knowledge_graph_edges.source_kind, knowledge_graph_edges.edge_kind',
      provider_write_executed: false,
    },
  ],
  content_graph_evidence_samples: [
    {
      sample_key: 'segment_hidden_1',
      source_kind: 'email_body',
      segment_kind: 'paragraph',
      segment_path: '/document[1]/paragraph[1]',
      word_count: 12,
    },
  ],
  knowledge_graph_evidence_samples: [
    {
      sample_key: 'edge_hidden_1',
      source_kind: 'email_body',
      edge_kind: 'node_has_segment',
      edge_path: '/document[1]/paragraph[1]/has/segment[1]',
      endpoint_status: 'segment_backed',
    },
  ],
  connector_events: [
    {
      event_uid: 'connector_evt_data_quality',
      signal_key: 'connector_heartbeat',
      state_code: 'heartbeat',
      detail_text: 'outbound connector heartbeat received',
      observed_at: '2026-05-28T05:45:00Z',
    },
  ],
};

const accountConfig = {
  user_id: 'default',
  smtp_server: 'smtp.example.com',
  smtp_port: 587,
  smtp_username: 'sender@example.com',
  has_smtp_password: true,
  imap_server: 'imap.example.com',
  imap_port: 993,
  imap_username: 'inbox@example.com',
  has_imap_password: true,
  pop3_server: 'pop3.example.com',
  pop3_port: 995,
  pop3_username: 'archive@example.com',
  has_pop3_password: false,
  oauth_client_id: 'oauth-client-id',
  oauth_redirect_uri: 'https://naruon.net/oauth/mail/callback',
  has_oauth_client_secret: true,
};

const llmProviders = [
  {
    id: 1,
    name: 'Primary OpenAI',
    provider_type: 'openai',
    base_url: 'https://api.openai.com/v1',
    model_identifier: 'gpt-4o',
    embedding_model: 'text-embedding-3-small',
    is_active: true,
    configured: true,
    fingerprint: '***1234',
    updated_at: '2026-06-11T04:00:00Z',
  },
  {
    id: 2,
    name: 'Local Gemma4',
    provider_type: 'ollama',
    base_url: 'http://ollama:11434/v1',
    model_identifier: 'gemma4:e2b-it-qat',
    embedding_model: 'embeddinggemma',
    is_active: true,
    configured: true,
    fingerprint: null,
    updated_at: '2026-06-11T05:00:00Z',
  },
];

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, OPTIONS',
};

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: CORS_HEADERS,
    body: JSON.stringify(body),
  });
}

export async function mockDashboardApi(page: Page, onApiRequest?: (path: string, request: Request) => void) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    onApiRequest?.(path, request);

    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: CORS_HEADERS,
      });
      return;
    }

    if (path === '/api/emails' && request.method() === 'GET') {
      if (url.searchParams.get('folder') === 'sent') {
        await fulfillJson(route, { emails: [sentEmail, selfSentNote, sentFollowUp, sentResolved, sentKnowledge] });
        return;
      }
      await fulfillJson(route, { emails: [email] });
      return;
    }

    if (path === '/api/emails/pending-replies' && request.method() === 'GET') {
      await fulfillJson(route, { emails: [sentEmail, sentFollowUp] });
      return;
    }

    if (path === '/api/prompts' && request.method() === 'GET') {
      await fulfillJson(route, aiHubPrompts);
      return;
    }

    if (path === '/api/ai-hub/surface' && request.method() === 'GET') {
      await fulfillJson(route, aiHubSurface);
      return;
    }

    if (path === '/api/runner-config' && request.method() === 'GET') {
      await fulfillJson(route, runnerConfig);
      return;
    }

    if (path === '/api/runner-config/rotate' && request.method() === 'POST') {
      await fulfillJson(route, {
        workspace_id: 'workspace-org-acme',
        configured: true,
        fingerprint: '***e2e',
        updated_at: '2026-05-27T07:00:00Z',
        connector_manifest: runnerConfig.connector_manifest,
      });
      return;
    }

    if (path === '/api/observability/operational-signals' && request.method() === 'GET') {
      await fulfillJson(route, operationalSignals);
      return;
    }

    if (path === '/api/security/access-surface' && request.method() === 'GET') {
      await fulfillJson(route, securityAccessSurface);
      return;
    }

    if (path === '/api/data/quality-surface' && request.method() === 'GET') {
      await fulfillJson(route, dataQualitySurface);
      return;
    }

    if (
      path === '/api/data/documents/doc_repository_ready/webdav-materialization-intent'
      && request.method() === 'POST'
    ) {
      await fulfillJson(route, {
        intent: 'document_webdav_materialization',
        status: 'completed',
        document_id: 'doc_repository_ready',
        workspace_id: 'workspace-org-acme',
        document_name: 'roadmap.md',
        document_type: 'text/markdown',
        source_id: 'webdav_src_primary',
        target_label: '운영 문서 원본',
        target_path: '/Naruon/Data/roadmap.md-opaque.md',
        requires_if_match: true,
        if_match: 'etag-webdav-primary',
        provenance: 'server-authoritative',
        provider_write_executed: true,
        audit_event: 'data.document.webdav_materialization.executed',
        runner_request_id: 'runner_req_data_doc_1',
        provider_status: 201,
        error_code: null,
        retry_item_uid: null,
        message: 'Workspace document WebDAV materialization executed by the connector.',
      });
      return;
    }

    if (path === '/api/accounts/config' && request.method() === 'GET') {
      await fulfillJson(route, accountConfig);
      return;
    }

    if (path === '/api/accounts/config' && request.method() === 'PUT') {
      const body = JSON.parse(request.postData() || '{}') as Record<string, unknown>;
      await fulfillJson(route, {
        ...accountConfig,
        smtp_server: body.smtp_server,
        smtp_port: body.smtp_port,
        smtp_username: body.smtp_username,
        imap_server: body.imap_server,
        imap_port: body.imap_port,
        imap_username: body.imap_username,
        pop3_server: body.pop3_server,
        pop3_port: body.pop3_port,
        pop3_username: body.pop3_username,
        oauth_client_id: body.oauth_client_id,
        oauth_redirect_uri: body.oauth_redirect_uri,
      });
      return;
    }

    if (path === '/api/llm-providers' && request.method() === 'GET') {
      await fulfillJson(route, llmProviders);
      return;
    }

    if (path === '/api/llm-providers' && request.method() === 'POST') {
      const body = JSON.parse(request.postData() || '{}') as Record<string, unknown>;
      await fulfillJson(route, {
        id: 3,
        name: body.name,
        provider_type: body.provider_type,
        base_url: body.base_url ?? null,
        model_identifier: body.model_identifier ?? null,
        embedding_model: body.embedding_model ?? null,
        is_active: body.is_active ?? true,
        configured: true,
        fingerprint: body.api_key ? '***1234' : null,
        updated_at: '2026-06-11T06:00:00Z',
      });
      return;
    }

    if (path.startsWith('/api/llm-providers/') && request.method() === 'PUT') {
      const body = JSON.parse(request.postData() || '{}') as Record<string, unknown>;
      const providerId = Number(path.split('/').at(-1));
      const provider = llmProviders.find((candidate) => candidate.id === providerId) ?? llmProviders[0];
      await fulfillJson(route, {
        ...provider,
        ...body,
        updated_at: '2026-06-11T06:30:00Z',
      });
      return;
    }

    if (path === '/api/search' && request.method() === 'POST') {
      let body: { query?: string } = {};
      try {
        body = JSON.parse(request.postData() || '{}') as { query?: string };
      } catch {
        body = {};
      }

      if (body.query?.includes('회의')) {
        await fulfillJson(route, { results: [calendarCandidate, sibling] });
        return;
      }

      await fulfillJson(route, { results: [email, mobileAttachmentResult, mobilePeopleResult] });
      return;
    }

    if (path === '/api/emails/7') {
      await fulfillJson(route, email);
      return;
    }

    if (path === '/api/emails/thread/thread-q2') {
      await fulfillJson(route, { thread: [email, sibling] });
      return;
    }

    if (path === '/api/llm/summarize') {
      await fulfillJson(route, {
        summary: '출시 일정, 마케팅 계획, 파트너 미팅을 하나의 실행 흐름으로 정리해야 합니다.',
        action_items: ['리소스 배정 검토 회의', '마케팅 캠페인 오프'],
      });
      return;
    }

    if (path === '/api/llm/draft') {
      await fulfillJson(route, { draft: '검토 후 일정과 우선순위를 정리해 공유드리겠습니다.' });
      return;
    }

    if (path === '/api/emails/send') {
      await fulfillJson(route, { simulated: true });
      return;
    }

    if (path === '/api/calendar/writeback-sources' && request.method() === 'GET') {
      await fulfillJson(route, [
        {
          source_id: 'caldav-primary',
          provider: 'Customer CalDAV',
          protocol: 'caldav',
          owner_id: 'default',
          organization_id: 'org-acme',
          capabilities: ['read', 'write', 'etag'],
          writeback_enabled: true,
          etag: 'etag-caldav-primary',
        },
      ]);
      return;
    }

    if (path === '/api/calendar/conflicts/evaluate' && request.method() === 'POST') {
      const payload = JSON.parse(request.postData() || '{}') as {
        existing_ics?: string;
      };
      if (payload.existing_ics?.includes('STATUS:CANCELLED')) {
        await fulfillJson(route, {
          decision_code: 'available',
          reason_code: 'no_overlapping_commitment',
          conflicts: [],
          recommended_action: 'Proceed with scheduling.',
          policy_version: 'status-weighted-v1',
        });
        return;
      }
      if (payload.existing_ics?.includes('STATUS:TENTATIVE')) {
        await fulfillJson(route, {
          decision_code: 'review_required',
          reason_code: 'lower_priority_conflict_requires_explicit_resolution',
          conflicts: [],
          recommended_action: 'Review the lower-priority conflict.',
          policy_version: 'status-weighted-v1',
        });
        return;
      }
      await fulfillJson(route, {
        decision_code: 'blocked',
        reason_code: 'equal_or_higher_priority_conflict',
        conflicts: [],
        recommended_action: 'Choose another time.',
        policy_version: 'status-weighted-v1',
      });
      return;
    }

    if (path === '/api/calendar/writeback-intent' && request.method() === 'POST') {
      await fulfillJson(route, {
        workspace_id: 'default',
        target_source_id: 'caldav-primary',
        protocol: 'caldav',
        writeback_mode: 'customer_owned',
        requires_if_match: false,
        if_match: null,
        provenance: {
          created_by: 'default',
          source_provider: 'Customer CalDAV',
          source_protocol: 'caldav',
        },
        audit_event: 'calendar.writeback_intent.created',
      });
      return;
    }

    if (path === '/api/webdav/accounts' && request.method() === 'GET') {
      await fulfillJson(route, [
        {
          source_id: 'webdav_src_primary',
          display_label: 'WebDAV source webdav_src_primary',
          writeback_enabled: true,
          etag: 'etag-webdav-primary',
        },
      ]);
      return;
    }

    if (path === '/api/webdav/folders' && request.method() === 'GET') {
      await fulfillJson(route, [
        {
          folder_uid: 'webdav_folder_roadmap',
          project_name: 'Naruon Roadmap 2026',
          webdav_path: '/Projects/Naruon_Roadmap_2026',
          owner_user_id: 'alice',
          organization_id: 'org-acme',
        },
        {
          folder_uid: 'webdav_folder_marketing',
          project_name: 'Marketing Assets',
          webdav_path: '/Projects/Marketing_Assets',
          owner_user_id: 'alice',
          organization_id: 'org-acme',
        },
      ]);
      return;
    }

    if (path === '/api/webdav/writeback-intent' && request.method() === 'POST') {
      await fulfillJson(route, {
        intent: 'writeback',
        source_id: 'webdav_src_primary',
        target_label: 'WebDAV source webdav_src_primary',
        requires_if_match: true,
        if_match: 'etag-webdav-primary',
        provenance: 'server-authoritative',
      });
      return;
    }

    if (path === '/api/emails/unique-thread-intent' && request.method() === 'POST') {
      await fulfillJson(route, {
        status: 'intent_ready',
        candidates_checked: 2,
        duplicates_found: 2,
        provider_write_executed: false,
        provenance: 'server-authoritative',
        audit_event: 'email.unique_thread_intent.created',
        thread_updates: [
          {
            candidate_key: 'zip-q2-root',
            canonical_thread_id: 'thread-q2-root',
            dedupe_key: 'q2-root@example.com',
            match_reason: 'message_id',
            existing_message_id: 'q2-root@example.com',
          },
          {
            candidate_key: 'forwarded-copy',
            canonical_thread_id: 'thread-q2-root',
            dedupe_key: 'sha256:duplicate',
            match_reason: 'fingerprint',
            existing_message_id: 'q2-root@example.com',
          },
        ],
      });
      return;
    }

    if (path === '/api/webdav/knowledge-materialization-intent' && request.method() === 'POST') {
      await fulfillJson(route, {
        intent: 'knowledge_materialization',
        status: 'intent_ready',
        task_id: 'task-self-knowledge',
        source_type: 'self_sent_knowledge',
        source_email_id: '<self-note@example.com>',
        source_thread_id: 'thread-self-note',
        source_id: 'webdav_src_primary',
        target_label: 'WebDAV source webdav_src_primary',
        target_path: '/Naruon/Notes/task-self-knowledge.md',
        requires_if_match: true,
        if_match: 'etag-webdav-primary',
        provenance: 'server-authoritative',
        provider_write_executed: false,
        audit_event: 'webdav.self_sent_knowledge_intent.created',
      });
      return;
    }

    if (path === '/api/tasks' && request.method() === 'GET') {
      await fulfillJson(route, [
        {
          id: 'task-q2-owner',
          title: '리소스 배정 검토 회의',
          status: 'blocked',
          priority: 'urgent',
          source_type: 'email',
          source_email_id: '<q2@example.com>',
          related_thread_id: 'thread-q2',
          created_at: '2026-05-19T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
        },
        {
          id: 'task-reply-followup',
          title: '보낸 메일 미답변 팔로업',
          status: 'in_progress',
          priority: 'high',
          source_type: 'email',
          source_email_id: '<sent-q2@example.com>',
          related_thread_id: 'thread-sent-q2',
          created_at: '2026-05-19T00:00:00Z',
          updated_at: '2026-05-22T00:00:00Z',
        },
        {
          id: 'task-calendar-writeback',
          title: '회의 후보 CalDAV 반영 검토',
          status: 'open',
          priority: 'normal',
          source_type: 'calendar',
          source_email_id: '<q2@example.com>',
          related_thread_id: 'thread-q2',
          created_at: '2026-05-19T00:00:00Z',
          updated_at: '2026-05-23T00:00:00Z',
        },
        {
          id: 'task-webdav-evidence',
          title: '첨부파일 WebDAV 폴더 정리',
          status: 'done',
          priority: 'low',
          source_type: 'webdav',
          source_email_id: '<q2@example.com>',
          related_thread_id: 'thread-q2',
          created_at: '2026-05-19T00:00:00Z',
          updated_at: '2026-05-24T00:00:00Z',
        },
        {
          id: 'task-self-knowledge',
          title: '나에게 보낸 지식 메모 정리',
          status: 'open',
          priority: 'normal',
          source_type: 'self_sent_knowledge',
          source_email_id: '<self-note@example.com>',
          related_thread_id: 'thread-self-note',
          created_at: '2026-05-19T00:00:00Z',
          updated_at: '2026-05-25T00:00:00Z',
        },
      ]);
      return;
    }

    if (path === '/api/tasks/from-email' && request.method() === 'POST') {
      await fulfillJson(route, {
        created: 2,
        tasks: [
          {
            id: 'task-q2-owner',
            title: '리소스 배정 검토 회의',
            status: 'open',
            priority: 'normal',
            source_type: 'email',
            source_email_id: '<q2@example.com>',
            related_thread_id: 'thread-q2',
            created_at: '2026-05-19T00:00:00Z',
            updated_at: '2026-05-19T00:00:00Z',
          },
          {
            id: 'task-q2-marketing',
            title: '마케팅 캠페인 오프',
            status: 'open',
            priority: 'normal',
            source_type: 'email',
            source_email_id: '<q2@example.com>',
            related_thread_id: 'thread-q2',
            created_at: '2026-05-19T00:00:00Z',
            updated_at: '2026-05-19T00:00:00Z',
          },
        ],
      });
      return;
    }

    if (path === '/api/tasks/reply-sla-escalations' && request.method() === 'POST') {
      await fulfillJson(route, {
        evaluated: 2,
        created: 1,
        policy: { overdue_hours: 48 },
        tasks: [
          {
            id: 'task-reply-followup',
            title: '미답변 팔로업: 벤더 계약 답변 요청',
            status: 'blocked',
            priority: 'urgent',
            source_type: 'reply_sla',
            source_email_id: '<sent-q2@example.com>',
            related_thread_id: 'thread-sent-q2',
            created_at: '2026-05-19T00:00:00Z',
            updated_at: '2026-05-27T08:30:00Z',
          },
        ],
      });
      return;
    }

    if (path === '/api/tasks/task-q2-owner' && request.method() === 'PATCH') {
      await fulfillJson(route, {
        id: 'task-q2-owner',
        title: '리소스 배정 검토 회의',
        status: 'done',
        priority: 'urgent',
        source_type: 'email',
        source_email_id: '<q2@example.com>',
        related_thread_id: 'thread-q2',
        created_at: '2026-05-19T00:00:00Z',
        updated_at: '2026-05-27T08:00:00Z',
      });
      return;
    }

    if (path === '/api/network/graph') {
      await fulfillJson(route, {
        nodes: [
          { id: 'sender-1', label: '김지현 PM', title: 'PM' },
          { id: 'owner-1', label: '사용자', title: 'Naruon owner' },
        ],
        edges: [{ source: 'sender-1', target: 'owner-1', weight: 2, title: '관련 메일' }],
      });
      return;
    }

    if (path === '/api/ontology/relationships' && request.method() === 'GET') {
      await fulfillJson(route, [
        {
          sender_email: 'jihyun@naruon.ai',
          parent_sender_email: 'user@naruon.ai',
          source_message_id: '<q2@example.com>',
          source_thread_id: 'thread-q2',
          relationship_type: 'colleague',
          confidence_score: 0.85,
          next_action: 'track_reply_and_tasks',
          action_reason: 'Same-domain sender; preserve reply and task follow-up.',
        },
      ]);
      return;
    }

    await route.fulfill({ status: 404, headers: CORS_HEADERS, body: 'Not mocked' });
  });
}
