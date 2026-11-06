import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DraftReview } from './DraftReview';
import { apiClient } from '../../api/client';
import { ApprovalResponse, DraftResponse, DraftVersionSummary } from '../../types';

vi.mock('../../api/client', () => ({
  apiClient: {
    getDraft: vi.fn(),
    getDraftVersions: vi.fn(),
    submitApprovalDecision: vi.fn(),
    editDraft: vi.fn(),
    markDraftPosted: vi.fn(),
    linkDraftPosted: vi.fn(),
  },
  ApiClientError: class ApiClientError extends Error {
    code: string;
    status: number;
    details?: Record<string, unknown>;
    constructor(msg: string, code: string, status: number, details?: Record<string, unknown>) {
      super(msg);
      this.code = code;
      this.status = status;
      this.details = details;
    }
  },
}));

describe('DraftReview (UI-04, UI-05, TEST-02)', () => {
  const mockDraftPending: DraftResponse = {
    id: 'draft-1',
    lineage_id: 'lin-100',
    version: 1,
    kind: 'script',
    platform: 'youtube',
    content: 'Hook: Want to write fast Python code?\nBody: Learn asyncio internals.\nCTA: Subscribe for more.',
    created_by: 'model',
    status: 'PENDING_APPROVAL',
    is_latest: true,
    critic_evaluation: {
      id: 'crit-1',
      draft_id: 'draft-1',
      review_number: 1,
      score: 8.5,
      passed: true,
      rubric: {
        hook: { score: 9.0, notes: 'Compelling question' },
        tone: { score: 8.0, notes: 'Engaging developer tone' },
        accuracy: { score: 9.0, notes: 'Technically sound' },
        length: { score: 8.5, notes: 'Within video pacing target' },
        relevance: { score: 8.0, notes: 'High niche match' },
      },
      deterministic: {
        passed: true,
        issues: [],
        missing_sections: [],
        metrics: { char_count: 85, word_count: 14 },
      },
      feedback: {
        strengths: ['Clear opening question', 'Strong CTA'],
        suggestions: ['Could elaborate on event loop metrics'],
        issues: [],
      },
      created_at: '2026-11-06T12:00:00Z',
    },
    created_at: '2026-11-06T12:00:00Z',
    updated_at: '2026-11-06T12:00:00Z',
  };

  const mockApproval: ApprovalResponse = {
    id: 'appr-1',
    item_type: 'draft',
    item_id: 'draft-1',
    status: 'PENDING',
    requested_at: '2026-11-06T12:00:00Z',
  };

  const mockVersions: DraftVersionSummary[] = [
    {
      version: 1,
      status: 'PENDING_APPROVAL',
      created_by: 'model',
      created_at: '2026-11-06T12:00:00Z',
      is_approved: false,
      is_posted: false,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.getDraft).mockResolvedValue(mockDraftPending);
    vi.mocked(apiClient.getDraftVersions).mockResolvedValue(mockVersions);
  });

  it('renders draft content, word/character counter, and critic rubric evaluation', async () => {
    render(<DraftReview approval={mockApproval} />);

    await waitFor(() => {
      expect(screen.getByText('Version 1')).toBeInTheDocument();
      expect(screen.getByText('YOUTUBE')).toBeInTheDocument();
      expect(screen.getByText('SCRIPT')).toBeInTheDocument();
      expect(screen.getByText(/Want to write fast Python code/)).toBeInTheDocument();
    });

    // Critic score and dimensions
    expect(screen.getByText('8.5')).toBeInTheDocument();
    expect(screen.getByText('Review 1 of 3')).toBeInTheDocument();
    expect(screen.getByText('Compelling question')).toBeInTheDocument();
    expect(screen.getByText('Clear opening question')).toBeInTheDocument();
  });

  it('displays the review limit reached banner when reviews are exhausted with open issues', async () => {
    const exhaustedDraft: DraftResponse = {
      ...mockDraftPending,
      critic_evaluation: {
        ...mockDraftPending.critic_evaluation!,
        review_number: 3,
        passed: false,
        score: 6.2,
        feedback: {
          issues: ['Pacing drags in middle', 'Missing concrete benchmark'],
          suggestions: ['Trim body explanation'],
        },
      },
    };
    vi.mocked(apiClient.getDraft).mockResolvedValue(exhaustedDraft);

    render(<DraftReview approval={mockApproval} />);

    await waitFor(() => {
      expect(screen.getByText(/Review Limit Reached/)).toBeInTheDocument();
      expect(
        screen.getByText(/This draft reached the maximum review iterations and still has open issues/)
      ).toBeInTheDocument();
      expect(screen.getByText('Pacing drags in middle')).toBeInTheDocument();
    });
  });

  it('allows approving draft and invokes approval decision API', async () => {
    const user = userEvent.setup();
    const onDecision = vi.fn();
    vi.mocked(apiClient.submitApprovalDecision).mockResolvedValue({
      approval: { ...mockApproval, status: 'DECIDED', decision: 'APPROVED' },
    });

    render(<DraftReview approval={mockApproval} onDecisionSubmitted={onDecision} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /approve/i }));

    expect(apiClient.submitApprovalDecision).toHaveBeenCalledWith('appr-1', {
      item_id: 'draft-1',
      decision: 'APPROVED',
    });
    expect(onDecision).toHaveBeenCalled();
  });

  it('allows rejecting draft with required feedback text in modal', async () => {
    const user = userEvent.setup();
    const onDecision = vi.fn();
    vi.mocked(apiClient.submitApprovalDecision).mockResolvedValue({
      approval: { ...mockApproval, status: 'DECIDED', decision: 'REJECTED' },
    });

    render(<DraftReview approval={mockApproval} onDecisionSubmitted={onDecision} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /reject with feedback/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /reject with feedback/i }));

    // Reject Modal opens
    const textarea = screen.getByPlaceholderText(/Explain what needs to change/);
    await user.type(textarea, 'Hook is too passive. Add concrete stats.');

    await user.click(screen.getByRole('button', { name: /^reject draft$/i }));

    expect(apiClient.submitApprovalDecision).toHaveBeenCalledWith('appr-1', {
      item_id: 'draft-1',
      decision: 'REJECTED',
      feedback_text: 'Hook is too passive. Add concrete stats.',
    });
    expect(onDecision).toHaveBeenCalled();
  });

  it('supports inline editing and validates deterministic quality checks before submission', async () => {
    const user = userEvent.setup();
    render(<DraftReview approval={mockApproval} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /edit inline/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit inline/i }));

    const editor = screen.getByPlaceholderText('Enter draft content...');
    // Clear and enter invalid content missing CTA and Hook
    await user.clear(editor);
    await user.type(editor, 'Some random body sentence with no sections.');

    await user.click(screen.getByRole('button', { name: /save and approve/i }));

    // Deterministic check warning appears
    expect(screen.getByText(/Draft checks failed:/)).toBeInTheDocument();
    expect(screen.getByText(/Missing required sections: Hook, CTA/)).toBeInTheDocument();
    expect(apiClient.submitApprovalDecision).not.toHaveBeenCalled();

    // Now fix content to include Hook, Body, and CTA
    await user.clear(editor);
    await user.type(editor, 'Hook: Quick tip.\nBody: Deep dive explanation.\nCTA: Subscribe!');

    vi.mocked(apiClient.submitApprovalDecision).mockResolvedValue({
      approval: { ...mockApproval, status: 'DECIDED', decision: 'EDITED' },
      resulting_item_id: 'draft-v2',
    });

    await user.click(screen.getByRole('button', { name: /save and approve/i }));

    expect(apiClient.submitApprovalDecision).toHaveBeenCalledWith('appr-1', {
      item_id: 'draft-1',
      decision: 'EDITED',
      edited_content: 'Hook: Quick tip.\nBody: Deep dive explanation.\nCTA: Subscribe!',
    });
  });

  it('warns that editing an already approved draft invalidates approval and creates a new version', async () => {
    const user = userEvent.setup();
    const approvedDraft: DraftResponse = {
      ...mockDraftPending,
      status: 'APPROVED',
    };
    vi.mocked(apiClient.getDraft).mockResolvedValue(approvedDraft);

    render(<DraftReview draftId="draft-1" />);

    await waitFor(() => {
      expect(screen.getByText('Approved')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /edit inline/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit inline/i }));

    expect(
      screen.getByText(/Saving creates a new version that needs approval\. The current approval will no longer apply\./)
    ).toBeInTheDocument();
  });

  it('supports copying approved draft to clipboard and marking as posted with link', async () => {
    const user = userEvent.setup();
    const approvedDraft: DraftResponse = {
      ...mockDraftPending,
      status: 'APPROVED',
    };
    vi.mocked(apiClient.getDraft).mockResolvedValue(approvedDraft);
    vi.mocked(apiClient.markDraftPosted).mockResolvedValue({
      draft_id: 'draft-1',
      status: 'POSTED',
      posted_ref: 'url',
      analytics_eligible: true,
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      configurable: true,
      writable: true,
    });

    render(<DraftReview draftId="draft-1" />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /mark as posted/i })).toBeInTheDocument();
    });

    // Test Copy
    await user.click(screen.getByRole('button', { name: /copy/i }));
    expect(writeTextMock).toHaveBeenCalledWith(approvedDraft.content);
    expect(screen.getByText('Copied!')).toBeInTheDocument();

    // Test Mark as Posted with URL
    await user.click(screen.getByRole('button', { name: /mark as posted/i }));

    const urlInput = screen.getByPlaceholderText(/https:\/\/youtube\.com\/watch\?v=/);
    await user.type(urlInput, 'https://youtube.com/watch?v=abc123xyz');

    await user.click(screen.getByRole('button', { name: /confirm mark as posted/i }));

    expect(apiClient.markDraftPosted).toHaveBeenCalledWith('draft-1', {
      posted_url: 'https://youtube.com/watch?v=abc123xyz',
      platform_content_id: undefined,
    });
  });

  it('marks draft as posted without link, displays "Posted (no link)" and allows adding link later', async () => {
    const user = userEvent.setup();
    const unlinkedPostedDraft: DraftResponse = {
      ...mockDraftPending,
      status: 'POSTED',
      posted_ref: 'none',
      posted_url: null,
      posted_platform_id: null,
    };
    vi.mocked(apiClient.getDraft).mockResolvedValue(unlinkedPostedDraft);
    vi.mocked(apiClient.linkDraftPosted).mockResolvedValue({
      ...unlinkedPostedDraft,
      posted_ref: 'url',
      posted_url: 'https://youtube.com/watch?v=newlink',
    });

    render(<DraftReview draftId="draft-1" />);

    await waitFor(() => {
      expect(screen.getByText('Posted (no link)')).toBeInTheDocument();
      expect(
        screen.getByText(/Automated metrics are unavailable until you add a link/)
      ).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /add link/i })[0]).toBeInTheDocument();
    });

    // Click Add link button
    await user.click(screen.getAllByRole('button', { name: /add link/i })[0]);

    const urlInput = screen.getByPlaceholderText('https://youtube.com/watch?v=...');
    await user.type(urlInput, 'https://youtube.com/watch?v=newlink');

    await user.click(screen.getByRole('button', { name: /attach link/i }));

    expect(apiClient.linkDraftPosted).toHaveBeenCalledWith('draft-1', {
      posted_url: 'https://youtube.com/watch?v=newlink',
      platform_content_id: undefined,
    });
  });

  it('shows warning when reviewing an outdated superseded draft version', async () => {
    const supersededDraft: DraftResponse = {
      ...mockDraftPending,
      status: 'SUPERSEDED',
    };
    vi.mocked(apiClient.getDraft).mockResolvedValue(supersededDraft);

    render(<DraftReview draftId="draft-1" />);

    await waitFor(() => {
      expect(
        screen.getByText(/This draft changed\. Reload to review the latest version\./)
      ).toBeInTheDocument();
    });
  });
});
