import React, { useState, useEffect } from 'react';
import {
  Inbox,
  Clock,
  ArrowRight,
  AlertCircle,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { ApprovalResponse, PlanDetails } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { PlanReview } from './PlanReview';

export interface ApprovalsInboxProps {
  initialApprovalId?: string | null;
  onClearInitialApprovalId?: () => void;
}

export const ApprovalsInbox: React.FC<ApprovalsInboxProps> = ({
  initialApprovalId,
  onClearInitialApprovalId,
}) => {
  const [approvals, setApprovals] = useState<ApprovalResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Selected approval for detailed review
  const [selectedApproval, setSelectedApproval] = useState<ApprovalResponse | null>(null);

  const fetchApprovals = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.listApprovals('PENDING');
      // Sort oldest first as specified in DESIGN 4.2
      const sorted = [...data].sort(
        (a, b) => new Date(a.requested_at).getTime() - new Date(b.requested_at).getTime()
      );
      setApprovals(sorted);

      if (initialApprovalId) {
        const found = sorted.find((a) => a.id === initialApprovalId);
        if (found) {
          setSelectedApproval(found);
        } else {
          // If not in pending, try fetching directly
          try {
            const single = await apiClient.getApproval(initialApprovalId);
            setSelectedApproval(single);
          } catch {
            // Stale or not found
          }
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load approvals.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApprovals();
  }, [initialApprovalId]);

  const handleDecisionSubmitted = () => {
    setSelectedApproval(null);
    if (onClearInitialApprovalId) onClearInitialApprovalId();
    fetchApprovals();
  };

  const formatWaitingDuration = (isoString: string): string => {
    const diff = Math.max(0, Date.now() - new Date(isoString).getTime());
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  const getItemTypeBadge = (itemType: string, briefId?: string | null) => {
    return (
      <div className="flex items-center gap-1.5">
        <Badge
          variant={
            itemType === 'plan'
              ? 'primary'
              : itemType === 'draft'
              ? 'info'
              : 'warning'
          }
          size="sm"
        >
          {itemType === 'plan'
            ? 'Plan'
            : itemType === 'draft'
            ? 'Draft'
            : 'Depth Increase'}
        </Badge>
        {itemType === 'plan' && briefId && (
          <Badge variant="info" size="sm">
            Weekly Brief
          </Badge>
        )}
      </div>
    );
  };

  // If viewing a single approval detail
  if (selectedApproval) {
    if (selectedApproval.item_type === 'plan') {
      return (
        <PlanReview
          approval={selectedApproval}
          onDecisionSubmitted={handleDecisionSubmitted}
          onBack={() => {
            setSelectedApproval(null);
            if (onClearInitialApprovalId) onClearInitialApprovalId();
          }}
        />
      );
    }

    // Fallback for draft or depth_increase in v1
    return (
      <div className="space-y-6">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setSelectedApproval(null)}
        >
          Back to Inbox
        </Button>
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-2">
            {getItemTypeBadge(selectedApproval.item_type, selectedApproval.brief_id)}
          </div>
          <h2 className="text-lg font-semibold text-[#0F172A] mb-2">
            Review {selectedApproval.item_type}
          </h2>
          <pre className="p-4 bg-slate-50 rounded-lg text-xs font-mono overflow-auto max-h-96">
            {JSON.stringify(selectedApproval.item_details || selectedApproval, null, 2)}
          </pre>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[#0F172A] tracking-tight">
            Approvals Inbox
          </h1>
          <p className="text-sm text-[#64748B] mt-1">
            Review and guide proposals before synthesis or execution proceeds.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchApprovals}
          isLoading={loading}
          leftIcon={<RefreshCw className="w-4 h-4" />}
        >
          Refresh
        </Button>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-xs text-[#DC2626] flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1 font-medium">{error}</div>
          <button
            onClick={fetchApprovals}
            className="font-semibold underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && approvals.length === 0 && (
        <div className="py-16 flex flex-col items-center justify-center text-[#64748B]">
          <Loader2 className="w-8 h-8 animate-spin text-[#6366F1] mb-3" />
          <p className="text-sm">Loading pending approvals...</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && approvals.length === 0 && !error && (
        <Card className="py-16 text-center">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-[#64748B] flex items-center justify-center mx-auto mb-3">
            <Inbox className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-[#0F172A] mb-1">
            Nothing is waiting for you.
          </h3>
          <p className="text-xs text-[#64748B] max-w-sm mx-auto">
            When a background strategist or weekly brief run requires your review, the pending request will appear here.
          </p>
        </Card>
      )}

      {/* Approvals list */}
      {approvals.length > 0 && (
        <div className="space-y-3">
          {approvals.map((appr) => {
            const planDetails = appr.item_details as PlanDetails | undefined;
            const title =
              planDetails?.items?.[0]?.topic ||
              (appr.item_type === 'plan'
                ? 'Proposed Content Plan'
                : `Review ${appr.item_type}`);

            return (
              <Card
                key={appr.id}
                onClick={() => setSelectedApproval(appr)}
                className="p-5 hover:border-indigo-200 hover:shadow-md transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="space-y-1.5 flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {getItemTypeBadge(appr.item_type, appr.brief_id)}
                    <span className="text-xs text-[#64748B] flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {formatWaitingDuration(appr.requested_at)}
                    </span>
                  </div>

                  <h3 className="text-base font-semibold text-[#0F172A] truncate">
                    {title}
                  </h3>

                  {planDetails?.items && (
                    <p className="text-xs text-[#64748B] line-clamp-1">
                      {planDetails.items.length} suggested item{planDetails.items.length === 1 ? '' : 's'} based on audience comments & research.
                    </p>
                  )}
                </div>

                <div className="shrink-0 flex items-center">
                  <Button
                    size="sm"
                    variant="primary"
                    rightIcon={<ArrowRight className="w-4 h-4" />}
                  >
                    Review
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
