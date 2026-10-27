import {
  ApprovalDecisionRequest,
  ApprovalDecisionResponse,
  ApprovalResponse,
  ChannelResolveResponse,
  CreatorChannelItem,
  DepthLevel,
  HealthResponse,
  OnboardingCompleteResponse,
  OnboardingResponse,
  PlanDetails,
  RoutingLogItem,
  RunResponse,
  SettingsResponse,
  SettingsUpdateRequest,
} from '../types';

export class ApiClientError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(message: string, code: string, status: number, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiClientError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const method = options.method?.toUpperCase() || 'GET';

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorCode = 'UNKNOWN_ERROR';
    let errorMessage = `Request failed with status ${response.status}`;
    let errorDetails: Record<string, unknown> | undefined;

    try {
      const errorJson = await response.json();
      if (errorJson.error) {
        errorCode = errorJson.error.code || errorCode;
        errorMessage = errorJson.error.message || errorMessage;
        errorDetails = errorJson.error.details;
      } else if (errorJson.detail) {
        errorMessage = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
        errorCode = 'VALIDATION_ERROR';
      }
    } catch {
      // Body not JSON
    }

    throw new ApiClientError(errorMessage, errorCode, response.status, errorDetails);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const apiClient = {
  // System Health
  getHealth: (): Promise<HealthResponse> =>
    request<HealthResponse>('/health'),

  // Onboarding
  getOnboarding: (): Promise<OnboardingResponse> =>
    request<OnboardingResponse>('/onboarding'),

  skipOnboardingChannel: (): Promise<void> =>
    request<void>('/onboarding/skip-channel', { method: 'POST' }),

  completeOnboarding: (): Promise<OnboardingCompleteResponse> =>
    request<OnboardingCompleteResponse>('/onboarding/complete', { method: 'POST' }),

  resolveChannel: (identifier: string): Promise<ChannelResolveResponse> =>
    request<ChannelResolveResponse>('/channel/resolve', {
      method: 'POST',
      body: JSON.stringify({ identifier }),
    }),

  getCreatorChannels: (): Promise<CreatorChannelItem[]> =>
    request<CreatorChannelItem[]>('/creator/channels'),

  updateCreatorChannel: (data: {
    identifier?: string;
    oauth_channel_id?: string;
  }): Promise<{ channel_id: string | null; handle: string | null; title: string | null; verified: boolean }> =>
    request('/creator/channel', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteCreatorChannel: (): Promise<void> =>
    request<void>('/creator/channel', { method: 'DELETE' }),

  // Settings
  getSettings: (): Promise<SettingsResponse> =>
    request<SettingsResponse>('/settings'),

  updateSettings: (data: SettingsUpdateRequest): Promise<SettingsResponse> =>
    request<SettingsResponse>('/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  startYouTubeOAuth: (returnTo: 'onboarding' | 'settings' = 'settings'): Promise<{ authorization_url: string }> =>
    request<{ authorization_url: string }>('/auth/youtube/start', {
      method: 'POST',
      body: JSON.stringify({ return_to: returnTo }),
    }),

  // Runs
  createRun: (data: {
    goal_text: string;
    depth_level?: DepthLevel;
  }): Promise<{ run_id: string; status: string }> =>
    request<{ run_id: string; status: string }>('/runs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listRuns: (status?: string, runType?: string): Promise<RunResponse[]> => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (runType) params.append('run_type', runType);
    const queryString = params.toString();
    return request<RunResponse[]>(`/runs${queryString ? `?${queryString}` : ''}`);
  },

  getRun: (runId: string): Promise<RunResponse> =>
    request<RunResponse>(`/runs/${runId}`),

  cancelRun: (runId: string): Promise<{ run_id: string; status: string }> =>
    request<{ run_id: string; status: string }>(`/runs/${runId}/cancel`, {
      method: 'POST',
    }),

  resumeRun: (runId: string): Promise<{ run_id: string; status: string }> =>
    request<{ run_id: string; status: string }>(`/runs/${runId}/resume`, {
      method: 'POST',
    }),

  getRunRoutingLog: (runId: string): Promise<RoutingLogItem[]> =>
    request<RoutingLogItem[]>(`/runs/${runId}/routing-log`),

  // Approvals
  listApprovals: (status?: string, itemType?: string): Promise<ApprovalResponse[]> => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (itemType) params.append('item_type', itemType);
    const queryString = params.toString();
    return request<ApprovalResponse[]>(`/approvals${queryString ? `?${queryString}` : ''}`);
  },

  getApproval: (approvalId: string): Promise<ApprovalResponse> =>
    request<ApprovalResponse>(`/approvals/${approvalId}`),

  submitApprovalDecision: (
    approvalId: string,
    data: ApprovalDecisionRequest
  ): Promise<ApprovalDecisionResponse> =>
    request<ApprovalDecisionResponse>(`/approvals/${approvalId}/decision`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Plans
  getPlan: (planId: string): Promise<PlanDetails> =>
    request<PlanDetails>(`/plans/${planId}`),

  editPlan: (
    planId: string,
    data: { expected_version: number; items: unknown[] }
  ): Promise<{ plan_id: string; approval_id: string }> =>
    request<{ plan_id: string; approval_id: string }>(`/plans/${planId}/edit`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
