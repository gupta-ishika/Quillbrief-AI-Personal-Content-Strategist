import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RunsScreen } from './RunsScreen';
import { apiClient } from '../../api/client';
import { RunResponse, RoutingLogItem } from '../../types';

vi.mock('../../api/client', () => ({
  apiClient: {
    listRuns: vi.fn(),
    getRun: vi.fn(),
    getRunRoutingLog: vi.fn(),
    cancelRun: vi.fn(),
    resumeRun: vi.fn(),
  },
}));

const mockRuns: RunResponse[] = [
  {
    id: 'run-1111-2222-3333-4444',
    goal_id: 'goal-1',
    run_type: 'goal',
    depth_level: 'standard',
    status: 'COMPLETED',
    step_count: 8,
    tokens_used: 12500,
    degraded: false,
    tasks: [
      {
        id: 't-1',
        run_id: 'run-1111-2222-3333-4444',
        title: 'Analyze comments',
        agent: 'listener',
        position: 1,
        status: 'DONE',
        created_at: '2026-11-06T10:00:00Z',
        updated_at: '2026-11-06T10:02:00Z',
      },
      {
        id: 't-2',
        run_id: 'run-1111-2222-3333-4444',
        title: 'Draft video script',
        agent: 'writer',
        position: 2,
        status: 'DONE',
        created_at: '2026-11-06T10:02:00Z',
        updated_at: '2026-11-06T10:05:00Z',
      },
    ],
    created_at: '2026-11-06T10:00:00Z',
    updated_at: '2026-11-06T10:06:00Z',
  },
  {
    id: 'run-5555-6666-7777-8888',
    goal_id: 'goal-2',
    run_type: 'goal',
    depth_level: 'quick',
    status: 'INTERRUPTED',
    step_count: 5,
    tokens_used: 8200,
    degraded: true,
    degraded_reason: 'Listener JSON parsing failed; used deterministic fallback.',
    tasks: [
      {
        id: 't-3',
        run_id: 'run-5555-6666-7777-8888',
        title: 'Gather comments',
        agent: 'listener',
        position: 1,
        status: 'DONE',
        created_at: '2026-11-06T11:00:00Z',
        updated_at: '2026-11-06T11:02:00Z',
      },
      {
        id: 't-4',
        run_id: 'run-5555-6666-7777-8888',
        title: 'Formulate strategy plan',
        agent: 'strategist',
        position: 2,
        status: 'TODO',
        created_at: '2026-11-06T11:02:00Z',
        updated_at: '2026-11-06T11:02:00Z',
      },
    ],
    created_at: '2026-11-06T11:00:00Z',
    updated_at: '2026-11-06T11:05:00Z',
  },
];

const mockLogs: RoutingLogItem[] = [
  {
    step_number: 1,
    from_node: 'supervisor',
    to_node: 'listener',
    reason: 'Established creator with stale comments needs audience insight analysis.',
    decided_by: 'model',
    eligible_nodes: ['listener', 'research'],
    output_status: 'valid',
    tokens_in: 450,
    tokens_out: 42,
    created_at: '2026-11-06T10:00:30Z',
  },
  {
    step_number: 2,
    from_node: 'listener',
    to_node: 'strategist',
    reason: 'Fresh audience comments gathered; moving to plan generation.',
    decided_by: 'code',
    eligible_nodes: ['strategist'],
    output_status: 'valid',
    tokens_in: 0,
    tokens_out: 0,
    created_at: '2026-11-06T10:02:00Z',
  },
];

describe('RunsScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.listRuns).mockResolvedValue(mockRuns);
    vi.mocked(apiClient.getRun).mockImplementation(async (id: string) => {
      const found = mockRuns.find((r) => r.id === id);
      if (!found) throw new Error('Not found');
      return found;
    });
    vi.mocked(apiClient.getRunRoutingLog).mockResolvedValue(mockLogs);
  });

  it('renders runs list with status, depth, steps, and tokens', async () => {
    render(<RunsScreen />);

    expect(screen.getByText('Loading runs history...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('run-1111...')).toBeInTheDocument();
      expect(screen.getByText('run-5555...')).toBeInTheDocument();
    });

    // Check status badges
    expect(screen.getAllByText('COMPLETED').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('INTERRUPTED').length).toBeGreaterThanOrEqual(2);

    // Check depth badges
    expect(screen.getByText('standard')).toBeInTheDocument();
    expect(screen.getByText('quick')).toBeInTheDocument();

    // Check tokens and steps
    expect(screen.getByText('8 steps')).toBeInTheDocument();
    expect(screen.getByText('12,500 tokens')).toBeInTheDocument();
  });

  it('filters runs by status', async () => {
    render(<RunsScreen />);

    await waitFor(() => {
      expect(screen.getByText('run-1111...')).toBeInTheDocument();
    });

    const completedFilterBtn = screen.getByRole('button', { name: 'COMPLETED' });
    fireEvent.click(completedFilterBtn);

    expect(apiClient.listRuns).toHaveBeenCalledWith('COMPLETED', undefined);
  });

  it('selects a run and displays run details, degraded notice, tasks, and routing timeline', async () => {
    render(<RunsScreen />);

    await waitFor(() => {
      expect(screen.getByText('run-5555...')).toBeInTheDocument();
    });

    // Click on the second (interrupted & degraded) run card
    const card = screen.getByText('run-5555...').closest('.cursor-pointer');
    expect(card).not.toBeNull();
    if (card) fireEvent.click(card);

    await waitFor(() => {
      // Degraded banner
      expect(screen.getByText('Degraded Run Notice')).toBeInTheDocument();
      expect(
        screen.getByText(/Listener JSON parsing failed; used deterministic fallback/)
      ).toBeInTheDocument();

      // Interrupted notice
      expect(screen.getByText('This run stopped before it finished')).toBeInTheDocument();

      // Routing log timeline item
      expect(screen.getByText('Routing Log Timeline (2)')).toBeInTheDocument();
      expect(
        screen.getByText('Established creator with stale comments needs audience insight analysis.')
      ).toBeInTheDocument();
      expect(screen.getByText('Model')).toBeInTheDocument();
      expect(screen.getByText('Code')).toBeInTheDocument();
    });

    // Switch to tasks tab
    const tasksTabBtn = screen.getByRole('button', { name: /Execution Tasks \(2\)/i });
    fireEvent.click(tasksTabBtn);

    expect(screen.getByText('Gather comments')).toBeInTheDocument();
    expect(screen.getByText('Formulate strategy plan')).toBeInTheDocument();
    expect(screen.getByText('TODO')).toBeInTheDocument();
  });

  it('resumes interrupted run when Resume button is clicked', async () => {
    vi.mocked(apiClient.resumeRun).mockResolvedValue({
      run_id: 'run-5555-6666-7777-8888',
      status: 'RUNNING',
    });

    render(<RunsScreen initialRunId="run-5555-6666-7777-8888" />);

    await waitFor(() => {
      expect(screen.getByText('This run stopped before it finished')).toBeInTheDocument();
    });

    const resumeBtns = screen.getAllByRole('button', { name: /Resume/i });
    fireEvent.click(resumeBtns[0]);

    await waitFor(() => {
      expect(apiClient.resumeRun).toHaveBeenCalledWith('run-5555-6666-7777-8888');
    });
  });

  it('cancels active run through confirmation modal', async () => {
    const runningRun: RunResponse = {
      ...mockRuns[0],
      id: 'run-running-9999',
      status: 'RUNNING',
    };
    vi.mocked(apiClient.getRun).mockResolvedValue(runningRun);
    vi.mocked(apiClient.cancelRun).mockResolvedValue({
      run_id: 'run-running-9999',
      status: 'STOPPED',
    });

    render(<RunsScreen initialRunId="run-running-9999" />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Cancel Run/i })).toBeInTheDocument();
    });

    // Click cancel button on header
    fireEvent.click(screen.getByRole('button', { name: /Cancel Run/i }));

    // Confirmation modal should open
    expect(screen.getByText('Cancel Execution Run?')).toBeInTheDocument();

    // Confirm cancel
    const confirmBtn = screen.getByRole('button', { name: 'Yes, Cancel Run' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(apiClient.cancelRun).toHaveBeenCalledWith('run-running-9999');
    });
  });
});
