import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';
import { apiClient } from './api/client';

vi.mock('./api/client', () => ({
  apiClient: {
    getOnboarding: vi.fn(),
    getHealth: vi.fn(),
    listApprovals: vi.fn(),
    getSettings: vi.fn(),
    listRuns: vi.fn(),
  },
}));

describe('App Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders onboarding wizard when onboarding is incomplete', async () => {
    vi.mocked(apiClient.getOnboarding).mockResolvedValue({
      onboarding_completed: false,
      next_step: 'niche',
      values: {
        niche: null,
        tone_preset: null,
        tone_instructions: null,
        channel: null,
        api_key_configured: false,
        youtube_oauth: { state: 'disconnected' },
      },
    });
    vi.mocked(apiClient.getHealth).mockResolvedValue({
      status: 'healthy',
      database_reachable: true,
      ollama_reachable: true,
      models: {
        llm: 'qwen3.5:4b',
        llm_installed: true,
        embedding: 'nomic-embed-text',
        embedding_installed: true,
        installed: true,
      },
      api_key_configured: false,
      scheduler_running: true,
      next_brief_at: null,
      interrupted_runs_count: 0,
    });
    vi.mocked(apiClient.getSettings).mockResolvedValue({
      default_depth_level: 'standard',
      brief_day: 'mon',
      brief_time: '08:00',
      time_zone: 'Asia/Kolkata',
      onboarding_completed: false,
    });

    render(<App />);

    expect(screen.getByText(/Connecting to local strategist/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Welcome to Quillbrief AI/i)).toBeInTheDocument();
      expect(screen.getByText(/Your niche/i)).toBeInTheDocument();
      expect(screen.getByText(/Step 1 of 4/i)).toBeInTheDocument();
    });
  });

  it('renders the app shell and sidebar when onboarding is completed', async () => {
    vi.mocked(apiClient.getOnboarding).mockResolvedValue({
      onboarding_completed: true,
      next_step: 'review',
      values: {
        niche: 'Python & AI',
        tone_preset: 'educational',
        tone_instructions: '',
        channel: null,
        api_key_configured: true,
        youtube_oauth: { state: 'disconnected' },
      },
    });
    vi.mocked(apiClient.getHealth).mockResolvedValue({
      status: 'healthy',
      database_reachable: true,
      ollama_reachable: true,
      models: {
        llm: 'qwen3.5:4b',
        llm_installed: true,
        embedding: 'nomic-embed-text',
        embedding_installed: true,
        installed: true,
      },
      api_key_configured: true,
      scheduler_running: true,
      next_brief_at: '2026-11-02T08:00:00Z',
      interrupted_runs_count: 0,
    });
    vi.mocked(apiClient.listApprovals).mockResolvedValue([]);
    vi.mocked(apiClient.listRuns).mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Quillbrief AI')).toBeInTheDocument();
      expect(screen.getByText('Content Strategist')).toBeInTheDocument();
      expect(screen.getByText('Create Strategy')).toBeInTheDocument();
    });
  });
});
