import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { OnboardingWizard } from './OnboardingWizard';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiClient: {
    getOnboarding: vi.fn(),
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
    resolveChannel: vi.fn(),
    updateCreatorChannel: vi.fn(),
    skipOnboardingChannel: vi.fn(),
    completeOnboarding: vi.fn(),
    startYouTubeOAuth: vi.fn(),
  },
  ApiClientError: class ApiClientError extends Error {
    code: string;
    status: number;
    constructor(msg: string, code: string, status: number) {
      super(msg);
      this.code = code;
      this.status = status;
    }
  },
}));

describe('OnboardingWizard', () => {
  const onCompleted = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Step 1 (Niche), enforces character counter and enables continue only when filled', async () => {
    vi.mocked(apiClient.getOnboarding).mockResolvedValue({
      onboarding_completed: false,
      next_step: 'niche',
      values: {
        niche: null,
        tone_preset: null,
        tone_instructions: null,
        channel: null,
        api_key_configured: true,
        youtube_oauth: { state: 'disconnected' },
      },
    });
    vi.mocked(apiClient.getSettings).mockResolvedValue({
      default_depth_level: 'standard',
      brief_day: 'mon',
      brief_time: '08:00',
      time_zone: 'Asia/Kolkata',
      onboarding_completed: false,
    });
    vi.mocked(apiClient.updateSettings).mockResolvedValue({} as any);

    const user = userEvent.setup();
    render(<OnboardingWizard onCompleted={onCompleted} />);

    await waitFor(() => {
      expect(screen.getByText('Your niche')).toBeInTheDocument();
      expect(screen.getByText('Step 1 of 4')).toBeInTheDocument();
    });

    const continueBtn = screen.getByRole('button', { name: /Continue/i });
    expect(continueBtn).toBeDisabled();

    const nicheInput = screen.getByPlaceholderText(/Python tutorials/i);
    await user.type(nicheInput, 'FastAPI Agents');

    expect(continueBtn).toBeEnabled();
    expect(screen.getByText('14/200')).toBeInTheDocument();

    await user.click(continueBtn);

    await waitFor(() => {
      expect(apiClient.updateSettings).toHaveBeenCalledWith({
        niche: 'FastAPI Agents',
      });
      expect(screen.getByText('Your tone')).toBeInTheDocument();
      expect(screen.getByText('Step 2 of 4')).toBeInTheDocument();
    });
  });

  it('resumes from server state at review step after channel skip', async () => {
    vi.mocked(apiClient.getOnboarding).mockResolvedValue({
      onboarding_completed: false,
      next_step: 'review',
      values: {
        niche: 'Fullstack React',
        tone_preset: 'conversational',
        tone_instructions: 'Keep it punchy',
        channel: null,
        api_key_configured: true,
        youtube_oauth: { state: 'disconnected' },
      },
    });
    vi.mocked(apiClient.getSettings).mockResolvedValue({
      default_depth_level: 'standard',
      brief_day: 'mon',
      brief_time: '08:00',
      time_zone: 'Asia/Kolkata',
      onboarding_completed: false,
      niche: 'Fullstack React',
      tone_preset: 'conversational',
      tone_instructions: 'Keep it punchy',
    });
    vi.mocked(apiClient.completeOnboarding).mockResolvedValue({
      onboarding_completed: true,
      next_brief_at: '2026-11-02T08:00:00Z',
    });

    const user = userEvent.setup();
    render(<OnboardingWizard onCompleted={onCompleted} />);

    await waitFor(() => {
      expect(screen.getByText('Review & Confirm')).toBeInTheDocument();
      expect(screen.getByText('Step 4 of 4')).toBeInTheDocument();
      expect(screen.getByText('Fullstack React')).toBeInTheDocument();
      expect(screen.getByText(/conversational/i)).toBeInTheDocument();
      expect(screen.getByText('Configured')).toBeInTheDocument();
    });

    const finishBtn = screen.getByRole('button', { name: /Finish setup/i });
    await user.click(finishBtn);

    await waitFor(() => {
      expect(apiClient.completeOnboarding).toHaveBeenCalled();
      expect(onCompleted).toHaveBeenCalled();
    });
  });
});
