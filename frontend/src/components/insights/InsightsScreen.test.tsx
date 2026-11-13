import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { InsightsScreen } from './InsightsScreen';
import { apiClient } from '../../api/client';
import {
  CommentInsightResponse,
  AnalystFindingResponse,
  StrategyEntryResponse,
} from '../../types';

vi.mock('../../api/client', () => ({
  apiClient: {
    getCommentInsights: vi.fn(),
    getFindings: vi.fn(),
    getStrategy: vi.fn(),
    getStrategyByKey: vi.fn(),
  },
}));

const mockCommentInsights: CommentInsightResponse[] = [
  {
    id: 'insight-1',
    creator_id: 'creator-1',
    run_id: 'run-1',
    theme_label: 'Asyncio vs Threading',
    comment_count: 34,
    coverage_analyzed: 100,
    coverage_total: 100,
    status: 'current',
    created_at: '2026-11-10T12:00:00Z',
    examples: [
      {
        comment_id: 'c-1',
        text: 'Can you show a real example of asyncio locks in production?',
        like_count: 25,
        published_at: '2026-11-09T10:00:00Z',
        available: true,
      },
      {
        comment_id: 'c-2',
        text: null,
        like_count: 12,
        published_at: '2026-08-01T10:00:00Z',
        available: false, // >90 days retention cleared
      },
    ],
  },
];

const mockFindings: AnalystFindingResponse[] = [
  {
    id: 'finding-1',
    run_id: 'run-1',
    draft_id: 'draft-101',
    finding: 'Short hooks (<15s) increase average view duration by 35%',
    recommendation: 'Keep all tutorial hooks under 15 seconds',
    confidence: 'high',
    sample_size: 15,
    evidence: { avg_duration_increase: 35, hook_threshold: 15 },
    created_at: '2026-11-10T14:00:00Z',
  },
  {
    id: 'finding-2',
    run_id: 'run-2',
    draft_id: null,
    finding: 'Sunday morning uploads have lower initial comment velocity',
    recommendation: 'Publish on Tuesday or Thursday afternoons',
    confidence: 'moderate',
    sample_size: 6,
    evidence: { weekday_delta: 28 },
    created_at: '2026-11-11T09:00:00Z',
  },
];

const mockStrategyEntries: StrategyEntryResponse[] = [
  {
    id: 'strat-1',
    creator_id: 'creator-1',
    key: 'preferred_hook_length',
    value: { max_seconds: 15 },
    reason: 'Data shows 35% higher view duration for hooks under 15s',
    supporting_finding_ids: ['finding-1'],
    status: 'active',
    created_at: '2026-11-10T15:00:00Z',
  },
  {
    id: 'strat-0',
    creator_id: 'creator-1',
    key: 'preferred_hook_length',
    value: { max_seconds: 30 },
    reason: 'Initial baseline assumption',
    supporting_finding_ids: [],
    status: 'superseded',
    created_at: '2026-10-01T10:00:00Z',
  },
];

describe('InsightsScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.getCommentInsights).mockResolvedValue(mockCommentInsights);
    vi.mocked(apiClient.getFindings).mockResolvedValue(mockFindings);
    vi.mocked(apiClient.getStrategy).mockResolvedValue(
      mockStrategyEntries.filter((s) => s.status === 'active')
    );
  });

  it('renders loading state initially and then shows KPI strip and comment themes', async () => {
    render(<InsightsScreen />);

    expect(screen.getByText(/Loading audience insights/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Insights & Strategy Memory')).toBeInTheDocument();
    });

    // KPI cards & tabs
    expect(screen.getAllByText('Comment Themes').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Analyst Findings').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Strategy Rules').length).toBeGreaterThanOrEqual(1);

    // Theme card content
    expect(screen.getByText('Asyncio vs Threading')).toBeInTheDocument();
    expect(screen.getByText('34 comments')).toBeInTheDocument();

    // Available example comment
    expect(
      screen.getByText('Can you show a real example of asyncio locks in production?')
    ).toBeInTheDocument();

    // Retention expired example comment (ADR-033)
    expect(
      screen.getByText(/Example no longer available \(cleared after 90 days retention\)/i)
    ).toBeInTheDocument();
  });

  it('navigates to Analyst Findings tab and filters by confidence', async () => {
    render(<InsightsScreen />);

    await waitFor(() => {
      expect(screen.getByText('Asyncio vs Threading')).toBeInTheDocument();
    });

    // Click on Analyst Findings tab
    const findingsTab = screen.getByRole('tab', { name: /Analyst Findings/i });
    fireEvent.click(findingsTab);

    // Should display findings
    expect(
      screen.getByText('Short hooks (<15s) increase average view duration by 35%')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Sunday morning uploads have lower initial comment velocity')
    ).toBeInTheDocument();

    // Check confidence badges
    expect(screen.getByText('high confidence')).toBeInTheDocument();
    expect(screen.getByText('moderate confidence')).toBeInTheDocument();

    // Filter by high confidence
    const highFilterBtn = screen.getByRole('button', { name: 'high' });
    fireEvent.click(highFilterBtn);

    expect(
      screen.getByText('Short hooks (<15s) increase average view duration by 35%')
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Sunday morning uploads have lower initial comment velocity')
    ).not.toBeInTheDocument();
  });

  it('navigates to Strategy Memory tab and toggles superseded history', async () => {
    render(<InsightsScreen />);

    await waitFor(() => {
      expect(screen.getByText('Asyncio vs Threading')).toBeInTheDocument();
    });

    // Click on Strategy Memory tab
    const strategyTab = screen.getByRole('tab', { name: /Strategy Memory/i });
    fireEvent.click(strategyTab);

    expect(screen.getByText('preferred_hook_length')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(
      screen.getByText('Data shows 35% higher view duration for hooks under 15s')
    ).toBeInTheDocument();

    // Now mock getStrategy to return history when include=history
    vi.mocked(apiClient.getStrategy).mockResolvedValueOnce(mockStrategyEntries);

    // Toggle history checkbox
    const historyCheckbox = screen.getByRole('checkbox');
    fireEvent.click(historyCheckbox);

    await waitFor(() => {
      expect(apiClient.getStrategy).toHaveBeenCalledWith({ include: 'history' });
    });
  });

  it('renders empty states when no data is returned', async () => {
    vi.mocked(apiClient.getCommentInsights).mockResolvedValue([]);
    vi.mocked(apiClient.getFindings).mockResolvedValue([]);
    vi.mocked(apiClient.getStrategy).mockResolvedValue([]);

    render(<InsightsScreen />);

    await waitFor(() => {
      expect(screen.getByText('No Comment Themes Found')).toBeInTheDocument();
    });

    // Switch to findings
    fireEvent.click(screen.getByRole('tab', { name: /Analyst Findings/i }));
    expect(screen.getByText('No Analyst Findings')).toBeInTheDocument();

    // Switch to strategy
    fireEvent.click(screen.getByRole('tab', { name: /Strategy Memory/i }));
    expect(screen.getByText('No Strategy Rules Recorded')).toBeInTheDocument();
  });

  it('handles error state and allows retry', async () => {
    vi.mocked(apiClient.getCommentInsights).mockRejectedValueOnce(
      new Error('Database offline')
    );

    render(<InsightsScreen />);

    await waitFor(() => {
      expect(screen.getByText('Database offline')).toBeInTheDocument();
    });

    const retryBtn = screen.getByRole('button', { name: /Try Again/i });
    expect(retryBtn).toBeInTheDocument();

    // On retry, succeed
    vi.mocked(apiClient.getCommentInsights).mockResolvedValue(mockCommentInsights);
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(screen.getByText('Asyncio vs Threading')).toBeInTheDocument();
    });
  });
});
