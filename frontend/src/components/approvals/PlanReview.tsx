import React, { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  Edit3,
  Trash2,
  Plus,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  ArrowLeft,
} from 'lucide-react';
import { apiClient, ApiClientError } from '../../api/client';
import {
  ApprovalResponse,
  PlanDetails,
  PlanItemResponse,
  SourceType,
} from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { Modal } from '../common/Modal';

export interface PlanReviewProps {
  approval: ApprovalResponse;
  onDecisionSubmitted: () => void;
  onBack?: () => void;
}

export const PlanReview: React.FC<PlanReviewProps> = ({
  approval,
  onDecisionSubmitted,
  onBack,
}) => {
  const plan = approval.item_details as PlanDetails | undefined;

  // Local state of plan items for editing
  const [items, setItems] = useState<PlanItemResponse[]>(
    plan?.items ? JSON.parse(JSON.stringify(plan.items)) : []
  );
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [expandedEvidence, setExpandedEvidence] = useState<Record<string, boolean>>({});

  // Rejection modal state
  const [rejectModalOpen, setRejectModalOpen] = useState<boolean>(false);
  const [feedbackText, setFeedbackText] = useState<string>('');

  // Submitting states
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const toggleEvidence = (itemId: string) => {
    setExpandedEvidence((prev) => ({
      ...prev,
      [itemId]: !prev[itemId],
    }));
  };

  const handleDropItem = (index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handleItemChange = (index: number, field: keyof PlanItemResponse, value: string | number) => {
    setItems((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const handleAddItem = () => {
    const newItem: PlanItemResponse = {
      id: `temp-${Date.now()}`,
      plan_id: plan?.id || '',
      item_key: `custom-${Date.now()}`,
      topic: 'New Strategy Topic',
      format: 'Video tutorial',
      platform: 'YouTube',
      objective: 'Audience acquisition',
      reason: 'Creator defined topic based on domain expertise',
      source_type: 'own_idea',
      priority: 1,
      status: 'PLANNED',
    };
    setItems((prev) => [...prev, newItem]);
    setIsEditing(true);
  };

  // 1. Approve Plan
  const handleApprove = async () => {
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await apiClient.submitApprovalDecision(approval.id, {
        item_id: approval.item_id,
        decision: 'APPROVED',
      });
      onDecisionSubmitted();
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.code === 'STALE_APPROVAL') {
        setErrorMessage('This item changed. Open the latest version to review it.');
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to approve plan.';
        setErrorMessage(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // 2. Reject Plan with Feedback
  const handleConfirmReject = async () => {
    const trimmed = feedbackText.trim();
    if (!trimmed) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await apiClient.submitApprovalDecision(approval.id, {
        item_id: approval.item_id,
        decision: 'REJECTED',
        feedback_text: trimmed,
      });
      setRejectModalOpen(false);
      onDecisionSubmitted();
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.code === 'STALE_APPROVAL') {
        setErrorMessage('This item changed. Open the latest version to review it.');
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to reject plan.';
        setErrorMessage(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // 3. Save Edits and Approve
  const handleSaveEdits = async () => {
    if (items.length === 0) {
      setErrorMessage('Plan must contain at least one item.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await apiClient.submitApprovalDecision(approval.id, {
        item_id: approval.item_id,
        decision: 'EDITED',
        edited_content: items.map((it) => ({
          item_key: it.item_key,
          topic: it.topic,
          format: it.format,
          platform: it.platform,
          objective: it.objective,
          reason: it.reason,
          source_type: it.source_type,
          source_ref: it.source_ref,
          priority: it.priority,
        })),
      });
      onDecisionSubmitted();
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.code === 'STALE_APPROVAL') {
        setErrorMessage('This item changed. Open the latest version to review it.');
      } else if (err instanceof ApiClientError && err.code === 'CHECKS_FAILED') {
        setErrorMessage('Plan checks failed. Please inspect your edits.');
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to save edited plan.';
        setErrorMessage(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const getSourceBadgeVariant = (src: SourceType): 'primary' | 'success' | 'info' => {
    switch (src) {
      case 'comment':
        return 'primary';
      case 'similar_creator':
        return 'info';
      case 'own_idea':
      default:
        return 'success';
    }
  };

  const getSourceLabel = (src: SourceType): string => {
    switch (src) {
      case 'comment':
        return 'Audience Comment';
      case 'similar_creator':
        return 'Similar Creator';
      case 'own_idea':
      default:
        return 'Own Idea';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header with back navigation & Version info */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
        <div className="flex items-center gap-3">
          {onBack && (
            <Button
              variant="outline"
              size="sm"
              onClick={onBack}
              leftIcon={<ArrowLeft className="w-4 h-4" />}
            >
              Back
            </Button>
          )}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wider">
                Plan Review
              </span>
              <Badge variant="primary" size="sm">
                Version {plan?.version || 1}
              </Badge>
              {approval.brief_id && (
                <Badge variant="info" size="sm">
                  Weekly Brief
                </Badge>
              )}
            </div>
            <h1 className="text-xl font-semibold text-[#0F172A]">
              Content Strategy Proposal
            </h1>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex items-center gap-2">
          {isEditing ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setItems(plan?.items ? JSON.parse(JSON.stringify(plan.items)) : []);
                  setIsEditing(false);
                }}
                disabled={isSubmitting}
              >
                Cancel Edits
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleSaveEdits}
                isLoading={isSubmitting}
                leftIcon={<CheckCircle2 className="w-4 h-4" />}
              >
                Save & Approve New Version
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsEditing(true)}
                leftIcon={<Edit3 className="w-4 h-4" />}
                disabled={isSubmitting}
              >
                Edit Plan
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setRejectModalOpen(true)}
                leftIcon={<XCircle className="w-4 h-4" />}
                disabled={isSubmitting}
              >
                Reject with Feedback
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleApprove}
                isLoading={isSubmitting}
                leftIcon={<CheckCircle2 className="w-4 h-4" />}
              >
                Approve Plan
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Editing Notice Banner */}
      {isEditing && (
        <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-200 text-xs text-[#6366F1] flex items-start gap-3">
          <Edit3 className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block mb-0.5">Editing Mode Active</span>
            <span>
              Saving creates a new plan version that requires approval. The earlier version will be archived.
            </span>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {errorMessage && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-xs text-[#DC2626] flex items-start gap-3">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1 font-medium">{errorMessage}</div>
          <button
            onClick={() => setErrorMessage(null)}
            className="font-semibold underline hover:no-underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Plan items card list */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-[#0F172A] uppercase tracking-wider">
            Strategy Items ({items.length})
          </span>
          {isEditing && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleAddItem}
              leftIcon={<Plus className="w-4 h-4" />}
            >
              Add Item
            </Button>
          )}
        </div>

        {items.map((item, index) => {
          const isEvidenceOpen = expandedEvidence[item.id || `item-${index}`];
          return (
            <Card key={item.id || index} className="p-5 space-y-4 transition-all">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex-1 min-w-[240px]">
                  {isEditing ? (
                    <input
                      type="text"
                      value={item.topic}
                      onChange={(e) => handleItemChange(index, 'topic', e.target.value)}
                      placeholder="Topic title"
                      className="w-full px-3 py-1.5 border border-[#E2E8F0] rounded-lg text-sm font-semibold text-[#0F172A]"
                    />
                  ) : (
                    <h3 className="text-base font-semibold text-[#0F172A]">
                      {item.topic}
                    </h3>
                  )}

                  <div className="flex flex-wrap items-center gap-2 mt-2">
                    <Badge variant="neutral" size="sm">
                      {item.platform}
                    </Badge>
                    <Badge variant="neutral" size="sm">
                      {item.format}
                    </Badge>
                    <button
                      type="button"
                      onClick={() => toggleEvidence(item.id || `item-${index}`)}
                      className="cursor-pointer"
                    >
                      <Badge
                        variant={getSourceBadgeVariant(item.source_type)}
                        size="sm"
                        className="flex items-center gap-1 hover:opacity-85"
                      >
                        <span>{getSourceLabel(item.source_type)}</span>
                        {isEvidenceOpen ? (
                          <ChevronUp className="w-3 h-3 ml-0.5" />
                        ) : (
                          <ChevronDown className="w-3 h-3 ml-0.5" />
                        )}
                      </Badge>
                    </button>
                  </div>
                </div>

                {isEditing && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDropItem(index)}
                    className="text-[#DC2626] hover:bg-red-50"
                    title="Drop item"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                )}
              </div>

              {/* Objective & Reason */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                <div className="p-3 bg-slate-50 rounded-lg border border-[#E2E8F0]">
                  <span className="text-[#64748B] font-semibold uppercase tracking-wider block mb-1">
                    Objective
                  </span>
                  {isEditing ? (
                    <input
                      type="text"
                      value={item.objective}
                      onChange={(e) => handleItemChange(index, 'objective', e.target.value)}
                      className="w-full px-2 py-1 border border-[#E2E8F0] rounded text-xs text-[#0F172A]"
                    />
                  ) : (
                    <p className="text-[#0F172A] font-medium leading-relaxed">
                      {item.objective}
                    </p>
                  )}
                </div>

                <div className="p-3 bg-slate-50 rounded-lg border border-[#E2E8F0]">
                  <span className="text-[#64748B] font-semibold uppercase tracking-wider block mb-1">
                    Strategic Rationale
                  </span>
                  {isEditing ? (
                    <textarea
                      rows={2}
                      value={item.reason}
                      onChange={(e) => handleItemChange(index, 'reason', e.target.value)}
                      className="w-full px-2 py-1 border border-[#E2E8F0] rounded text-xs text-[#0F172A]"
                    />
                  ) : (
                    <p className="text-[#0F172A] font-medium leading-relaxed">
                      {item.reason}
                    </p>
                  )}
                </div>
              </div>

              {/* Expandable Evidence Card */}
              {isEvidenceOpen && (
                <div className="p-3.5 bg-indigo-50/60 border border-indigo-100 rounded-lg text-xs space-y-1.5 animate-fadeIn">
                  <div className="flex items-center gap-1.5 font-semibold text-[#6366F1]">
                    <MessageSquare className="w-3.5 h-3.5" />
                    <span>Evidence Behind Suggestion</span>
                  </div>
                  <p className="text-[#0F172A]">
                    Source:{' '}
                    <span className="font-semibold capitalize">
                      {item.source_type.replace(/_/g, ' ')}
                    </span>
                  </p>
                  {item.source_ref ? (
                    <div className="p-2 bg-white rounded border border-indigo-100 font-mono text-[11px] text-[#64748B]">
                      {item.source_ref}
                    </div>
                  ) : (
                    <p className="text-[#64748B]">
                      Synthesized based on creator profile & domain focus areas.
                    </p>
                  )}
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {/* Reject with feedback Modal */}
      <Modal
        isOpen={rejectModalOpen}
        onClose={() => setRejectModalOpen(false)}
        title="Reject Content Plan"
        description="Provide feedback to guide the Strategist agent on revisions."
      >
        <div className="space-y-4">
          <div>
            <label
              htmlFor="rejection-feedback"
              className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-2"
            >
              Feedback & Adjustment Instructions *
            </label>
            <textarea
              id="rejection-feedback"
              rows={4}
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="e.g., Focus more on production troubleshooting rather than introductory theory. Include at least one short-form post."
              className="w-full px-3.5 py-2.5 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] placeholder-[#64748B]/60 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
            <p className="text-[11px] text-[#64748B] mt-1">
              Feedback is required so the multi-agent system understands what to adjust.
            </p>
          </div>

          <div className="flex justify-end gap-2.5 pt-2">
            <Button
              variant="outline"
              onClick={() => setRejectModalOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmReject}
              disabled={!feedbackText.trim()}
              isLoading={isSubmitting}
            >
              Submit Rejection
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
