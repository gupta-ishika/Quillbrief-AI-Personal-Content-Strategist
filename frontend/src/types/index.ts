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
  item_details?: PlanDetails | Record<string, unknown> | null;
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

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
