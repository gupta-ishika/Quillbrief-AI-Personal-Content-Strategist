import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { HomeScreen } from './HomeScreen';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiClient: {
    listRuns: vi.fn(),
    getRun: vi.fn(),
    createRun: vi.fn(),
    cancelRun: vi.fn(),
    resumeRun: vi.fn(),
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

describe('HomeScreen', () => {
  const onNavigateToApprovals = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders goal input, depth options and starts run on click', async () => {
    vi.mocked(apiClient.listRuns).mockResolvedValue([]);
    vi.mocked(apiClient.createRun).mockResolvedValue({
      run_id: 'run-123',
      status: 'PENDING',
    });
    vi.mocked(apiClient.getRun).mockResolvedValue({
      id: 'run-123',
      run_type: 'goal',
      depth_level: 'standard',
      status: 'RUNNING',
      step_count: 2,
      tokens_used: 1500,
      degraded: false,
      current_node: 'researcher_node',
      tasks: [
        {
          id: 'task-1',
          run_id: 'run-123',
          title: 'Extract comment topics',
          agent: 'Researcher',
          position: 1,
          status: 'DONE',
          created_at: '2026-10-27T10:00:00Z',
          updated_at: '2026-10-27T10:01:00Z',
        },
      ],
      created_at: '2026-10-27T10:00:00Z',
      updated_at: '2026-10-27T10:01:00Z',
    });

    const user = userEvent.setup();
    render(<HomeScreen onNavigateToApprovals={onNavigateToApprovals} />);

    expect(screen.getByText('Create Strategy')).toBeInTheDocument();
    expect(screen.getByText('Standard')).toBeInTheDocument();

    const startBtn = screen.getByRole('button', { name: /Start Strategy Run/i });
    expect(startBtn).toBeDisabled();

    const goalInput = screen.getByPlaceholderText(/Plan 3 technical tutorials/i);
    await user.type(goalInput, 'Build a multi-agent system');

    expect(startBtn).toBeEnabled();
    await user.click(startBtn);

    await waitFor(() => {
      expect(apiClient.createRun).toHaveBeenCalledWith({
        goal_text: 'Build a multi-agent system',
        depth_level: 'standard',
      });
      expect(screen.getByText('Active Run')).toBeInTheDocument();
      expect(screen.getByText('Extract comment topics')).toBeInTheDocument();
    });
  });

  it('displays degraded run notice banner when run is marked degraded', async () => {
    vi.mocked(apiClient.listRuns).mockResolvedValue([
      {
        id: 'run-deg',
        run_type: 'goal',
        depth_level: 'standard',
        status: 'RUNNING',
        step_count: 3,
        tokens_used: 2100,
        degraded: true,
        degraded_reason: 'YouTube API key not configured. Mock comments used.',
        current_node: 'strategist_node',
        tasks: [],
        created_at: '2026-10-27T10:00:00Z',
        updated_at: '2026-10-27T10:01:00Z',
      },
    ]);

    render(<HomeScreen onNavigateToApprovals={onNavigateToApprovals} />);

    await waitFor(() => {
      expect(screen.getByText(/Degraded Run Notice/i)).toBeInTheDocument();
      expect(screen.getByText(/Some steps used default choices or missing tools/i)).toBeInTheDocument();
      expect(screen.getByText(/YouTube API key not configured/i)).toBeInTheDocument();
    });
  });
});
