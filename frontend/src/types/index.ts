export type OnboardingStep = 'niche' | 'tone' | 'channel' | 'review';

export interface OnboardingChannelValue {
  channel_id?: string | null;
  handle?: string | null;
  title?: string | null;
  verified: boolean;
}

export interface OnboardingValues {
  niche?: string | null;
  tone_preset?: string | null;
  tone_instructions?: string | null;
  channel?: OnboardingChannelValue | null;
  api_key_configured: boolean;
  youtube_oauth: {
    state: 'connected' | 'needs_reauth' | 'disconnected';
  };
}

export interface OnboardingResponse {
  onboarding_completed: boolean;
  next_step: OnboardingStep;
  values: OnboardingValues;
}

export interface OnboardingCompleteResponse {
  onboarding_completed: boolean;
  next_brief_at: string | null;
}

export interface ChannelResolveResponse {
  resolved: boolean;
  channel_id?: string | null;
  title?: string | null;
  reason?: string | null;
  parsed?: {
    type: 'handle' | 'channel_id';
    value: string;
  } | null;
}

export interface CreatorChannelItem {
  channel_id: string;
  title: string;
  custom_url?: string | null;
  thumbnail_url?: string | null;
}

export type TonePreset =
  | 'professional'
  | 'friendly'
  | 'educational'
  | 'conversational'
  | 'humorous';

export type DepthLevel = 'quick' | 'standard' | 'deep';

export interface SettingsResponse {
  default_depth_level: DepthLevel;
  brief_day: string;
  brief_time: string;
  time_zone: string;
  niche?: string | null;
  tone_preset?: TonePreset | null;
  tone_instructions?: string | null;
  onboarding_completed: boolean;
  next_brief_at?: string | null;
}

export interface SettingsUpdateRequest {
  default_depth_level?: DepthLevel;
  brief_day?: string;
  brief_time?: string;
  time_zone?: string;
  niche?: string;
  tone_preset?: TonePreset;
  tone_instructions?: string;
}

export type RunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'WAITING_APPROVAL'
  | 'COMPLETED'
  | 'FAILED'
  | 'STOPPED'
  | 'INTERRUPTED';

export type RunType = 'goal' | 'weekly_brief' | 'post_mortem';
export type TaskStatus = 'TODO' | 'DONE' | 'SKIPPED' | 'FAILED';

export interface TaskResponse {
  id: string;
  run_id: string;
  title: string;
  agent: string;
  position: number;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
}

export interface RunResponse {
  id: string;
  goal_id?: string | null;
  run_type: RunType;
  depth_level: DepthLevel;
  status: RunStatus;
  step_count: number;
  tokens_used: number;
  stop_reason?: string | null;
  degraded: boolean;
  degraded_reason?: string | null;
  current_node?: string | null;
  tasks: TaskResponse[];
  pending_approval_id?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RoutingLogItem {
  step_number: number;
  from_node: string;
  to_node: string;
  reason: string;
  decided_by: 'model' | 'code';
  eligible_nodes: string[];
  output_status: 'valid' | 'retried_valid' | 'fallback';
  invalid_category?: 'bad_json' | 'schema_violation' | 'ineligible_node' | 'timeout' | null;
  tokens_in: number;
  tokens_out: number;
  created_at: string;
}

export type ApprovalItemType = 'plan' | 'draft' | 'depth_increase';
export type ApprovalStatus = 'PENDING' | 'DECIDED' | 'CANCELLED';
export type ApprovalDecision = 'APPROVED' | 'REJECTED' | 'EDITED';

export type PlanStatus =
  | 'DRAFT'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'SUPERSEDED';

export type PlanItemStatus = 'PLANNED' | 'DRAFTING' | 'DONE' | 'DROPPED';
export type SourceType = 'comment' | 'similar_creator' | 'own_idea';

export interface PlanItemResponse {
  id: string;
  plan_id: string;
  item_key: string;
  topic: string;
  format: string;
  platform: string;
  objective: string;
  reason: string;
  source_type: SourceType;
  source_ref?: string | null;
  priority: number;
  scheduled_day?: string | null;
  status: PlanItemStatus;
}

export interface PlanDetails {
  id: string;
  lineage_id: string;
  version: number;
  status: PlanStatus;
  created_by: 'strategist' | 'creator';
  feedback_text?: string | null;
  items: PlanItemResponse[];
}

export interface ApprovalResponse {
  id: string;
  run_id?: string | null;
  item_type: ApprovalItemType;
  item_id: string;
  status: ApprovalStatus;
  decision?: ApprovalDecision | null;
  feedback_text?: string | null;
  edited_content?: unknown;
  resulting_item_id?: string | null;
  brief_id?: string | null;
  item_details?: PlanDetails | DraftResponse | Record<string, unknown> | null;
  requested_at: string;
  decided_at?: string | null;
}

export interface ApprovalDecisionRequest {
  item_id: string;
  decision: ApprovalDecision;
  feedback_text?: string | null;
  edited_content?: unknown;
}

export interface ApprovalDecisionResponse {
  approval: ApprovalResponse;
  resulting_item_id?: string | null;
  resumed_run_id?: string | null;
}

export type DraftKind =
  | 'script'
  | 'title'
  | 'description'
  | 'community_post'
  | 'caption'
  | 'linkedin_post'
  | 'x_thread';

export type DraftStatus =
  | 'WRITING'
  | 'IN_REVIEW'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'SUPERSEDED'
  | 'POSTED';

export interface CriticRubricItem {
  score: number;
  notes: string;
}

export interface CriticDeterministicResult {
  passed: boolean;
  issues?: string[];
  missing_sections?: string[];
  metrics?: Record<string, number>;
}

export interface CriticFeedbackResult {
  issues?: string[];
  strengths?: string[];
  suggestions?: string[];
}

export interface CriticEvaluationResponse {
  id: string;
  draft_id: string;
  review_number: number;
  score: number;
  passed: boolean;
  rubric: Record<string, CriticRubricItem>;
  deterministic: CriticDeterministicResult;
  feedback: CriticFeedbackResult;
  created_at: string;
}

export interface DraftResponse {
  id: string;
  lineage_id: string;
  version: number;
  previous_version_id?: string | null;
  plan_item_id?: string | null;
  item_key?: string | null;
  parent_draft_id?: string | null;
  kind: DraftKind;
  platform: string;
  content: string;
  created_by: 'model' | 'creator';
  status: DraftStatus;
  is_latest: boolean;
  critic_evaluation?: CriticEvaluationResponse | null;
  posted_at?: string | null;
  posted_ref?: 'url' | 'platform_id' | 'none' | null;
  posted_url?: string | null;
  posted_platform_id?: string | null;
  child_draft_ids?: string[];
  created_at: string;
  updated_at: string;
}

export interface DraftVersionSummary {
  version: number;
  status: DraftStatus;
  created_by: string;
  created_at: string;
  is_approved: boolean;
  is_posted: boolean;
}

export interface DraftEditRequest {
  content: string;
  expected_version: number;
}

export interface DraftEditResponse {
  draft_id: string;
  approval_id: string;
}

export interface MarkPostedRequest {
  posted_url?: string | null;
  platform_content_id?: string | null;
  posted_at?: string | null;
}

export interface MarkPostedResponse {
  draft_id: string;
  status: 'POSTED';
  posted_ref: 'url' | 'platform_id' | 'none';
  analytics_eligible: boolean;
}

export interface LinkPostedRequest {
  posted_url?: string | null;
  platform_content_id?: string | null;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  database_reachable: boolean;
  ollama_reachable: boolean;
  models: {
    llm: string;
    llm_installed: boolean;
    embedding: string;
    embedding_installed: boolean;
    installed: boolean;
  };
  api_key_configured: boolean;
  scheduler_running: boolean;
  next_brief_at: string | null;
  interrupted_runs_count: number;
}

export interface CommentInsightExample {
  comment_id: string;
  text: string | null;
  like_count: number;
  published_at: string;
  available: boolean;
}

export interface CommentInsightResponse {
  id: string;
  creator_id: string;
  run_id: string;
  theme_label: string;
  comment_count: number;
  examples: CommentInsightExample[];
  coverage_analyzed: number;
  coverage_total: number;
  status: 'current' | 'superseded';
  created_at: string;
}

export interface AnalystFindingResponse {
  id: string;
  run_id: string;
  draft_id?: string | null;
  finding: string;
  recommendation: string;
  confidence: 'low' | 'moderate' | 'high';
  sample_size: number;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface StrategyEntryResponse {
  id: string;
  creator_id: string;
  key: string;
  value: unknown;
  reason: string;
  supporting_finding_ids: string[];
  status: 'active' | 'superseded';
  created_at: string;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
