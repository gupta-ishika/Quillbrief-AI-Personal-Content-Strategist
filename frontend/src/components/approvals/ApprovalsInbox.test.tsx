import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApprovalsInbox } from './ApprovalsInbox';
import { apiClient } from '../../api/client';
import { ApprovalResponse } from '../../types';

vi.mock('../../api/client', () => ({
  apiClient: {
    listApprovals: vi.fn(),
    getApproval: vi.fn(),
    submitApprovalDecision: vi.fn(),
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

describe('ApprovalsInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when there are no pending approvals', async () => {
    vi.mocked(apiClient.listApprovals).mockResolvedValue([]);

    render(<ApprovalsInbox />);

    await waitFor(() => {
      expect(screen.getByText('Nothing is waiting for you.')).toBeInTheDocument();
    });
  });

  it('renders pending approvals and supports opening plan review, viewing items, and approving', async () => {
    const mockApproval: ApprovalResponse = {
      id: 'appr-1',
      run_id: 'run-1',
      item_type: 'plan',
      item_id: 'plan-ver-1',
      status: 'PENDING',
      requested_at: '2026-10-27T10:00:00Z',
      item_details: {
        id: 'plan-ver-1',
        lineage_id: 'lin-1',
        version: 1,
        status: 'PENDING_APPROVAL',
        created_by: 'strategist',
        items: [
          {
            id: 'item-1',
            plan_id: 'plan-ver-1',
            item_key: 'topic-fastapi',
            topic: 'Mastering FastAPI Middleware',
            format: 'Video tutorial',
            platform: 'YouTube',
            objective: 'Deepen backend engineering authority',
            reason: 'High audience search demand on middleware debugging',
            source_type: 'comment',
            source_ref: 'Comment ID: 98762',
            priority: 1,
            status: 'PLANNED',
          },
        ],
      },
    };

    vi.mocked(apiClient.listApprovals).mockResolvedValue([mockApproval]);
    vi.mocked(apiClient.submitApprovalDecision).mockResolvedValue({
      approval: { ...mockApproval, status: 'DECIDED', decision: 'APPROVED' },
    });

    const user = userEvent.setup();
    render(<ApprovalsInbox />);

    await waitFor(() => {
      expect(screen.getByText('Mastering FastAPI Middleware')).toBeInTheDocument();
    });

    // Click Review button
    const reviewBtn = screen.getByRole('button', { name: /Review/i });
    await user.click(reviewBtn);

    await waitFor(() => {
      expect(screen.getByText('Content Strategy Proposal')).toBeInTheDocument();
      expect(screen.getByText('Version 1')).toBeInTheDocument();
      expect(screen.getByText('Audience Comment')).toBeInTheDocument();
      expect(screen.getByText('Deepen backend engineering authority')).toBeInTheDocument();
    });

    // Click Approve Plan
    const approveBtn = screen.getByRole('button', { name: /Approve Plan/i });
    await user.click(approveBtn);

    await waitFor(() => {
      expect(apiClient.submitApprovalDecision).toHaveBeenCalledWith('appr-1', {
        item_id: 'plan-ver-1',
        decision: 'APPROVED',
      });
    });
  });
});
