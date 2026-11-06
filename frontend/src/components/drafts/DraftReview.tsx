import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  XCircle,
  Edit3,
  Copy,
  Check,
  Share2,
  Link as LinkIcon,
  AlertTriangle,
  AlertCircle,
  ArrowLeft,
  ChevronDown,
  ExternalLink,
  ShieldAlert,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { apiClient, ApiClientError } from '../../api/client';
import {
  ApprovalResponse,
  DraftResponse,
  DraftVersionSummary,
} from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { Modal } from '../common/Modal';

export interface DraftReviewProps {
  approval?: ApprovalResponse;
  draftId?: string;
  onDecisionSubmitted?: () => void;
  onBack?: () => void;
  onDraftUpdated?: (updatedDraft: DraftResponse) => void;
}

export const PLATFORM_LIMITS: Record<string, { maxChars: number; label: string }> = {
  'youtube-title': { maxChars: 100, label: 'YouTube Title (100 chars)' },
  'youtube-description': { maxChars: 5000, label: 'YouTube Description (5,000 chars)' },
  'youtube-community_post': { maxChars: 5000, label: 'YouTube Community Post (5,000 chars)' },
  'instagram-caption': { maxChars: 2200, label: 'Instagram Caption (2,200 chars)' },
  'linkedin-linkedin_post': { maxChars: 3000, label: 'LinkedIn Post (3,000 chars)' },
  'x-x_thread': { maxChars: 280, label: 'X Thread / Tweet (280 chars per tweet)' },
};

export const getPlatformLimit = (platform: string, kind: string): { maxChars: number; label: string } | null => {
  const normPlatform = (platform || '').toLowerCase();
  const normKind = (kind || '').toLowerCase();

  const exactKey = `${normPlatform}-${normKind}`;
  if (PLATFORM_LIMITS[exactKey]) return PLATFORM_LIMITS[exactKey];

  if (normPlatform === 'youtube' && normKind === 'title') return PLATFORM_LIMITS['youtube-title'];
  if (normPlatform === 'youtube' && (normKind === 'description' || normKind === 'script')) return PLATFORM_LIMITS['youtube-description'];
  if (normPlatform === 'instagram') return PLATFORM_LIMITS['instagram-caption'];
  if (normPlatform === 'linkedin') return PLATFORM_LIMITS['linkedin-linkedin_post'];
  if (normPlatform === 'x' || normPlatform === 'twitter') return PLATFORM_LIMITS['x-x_thread'];

  return null;
};

export const checkDeterministicRequirements = (
  content: string,
  kind: string,
  platform: string
): { passed: boolean; issues: string[]; missing_sections: string[] } => {
  const issues: string[] = [];
  const missing_sections: string[] = [];
  const lower = content.toLowerCase();

  // Section checks for formats that require Hook, Body, CTA
  const requiresSections = ['script', 'post', 'linkedin_post', 'caption', 'community_post', 'x_thread'].includes(
    kind.toLowerCase()
  );

  if (requiresSections) {
    const hasHook = lower.includes('hook') || lower.includes('intro');
    const hasBody = lower.includes('body') || lower.includes('main') || content.trim().length > 80;
    const hasCta = lower.includes('cta') || lower.includes('call to action') || lower.includes('subscribe') || lower.includes('follow') || lower.includes('comment') || lower.includes('link in');

    if (!hasHook) missing_sections.push('Hook');
    if (!hasBody) missing_sections.push('Body');
    if (!hasCta) missing_sections.push('CTA');
  }

  // Length checks
  const limitInfo = getPlatformLimit(platform, kind);
  if (limitInfo && content.length > limitInfo.maxChars) {
    issues.push(`Content length (${content.length} chars) exceeds platform limit of ${limitInfo.maxChars} chars.`);
  }

  if (missing_sections.length > 0) {
    issues.push(`Missing required sections: ${missing_sections.join(', ')}.`);
  }

  return {
    passed: issues.length === 0,
    issues,
    missing_sections,
  };
};

export const DraftReview: React.FC<DraftReviewProps> = ({
  approval,
  draftId: propDraftId,
  onDecisionSubmitted,
  onBack,
  onDraftUpdated,
}) => {
  const effectiveDraftId = propDraftId || approval?.item_id || '';

  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [versions, setVersions] = useState<DraftVersionSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Editing state
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editContent, setEditContent] = useState<string>('');
  const [editErrors, setEditErrors] = useState<string[]>([]);

  // Action modals
  const [rejectModalOpen, setRejectModalOpen] = useState<boolean>(false);
  const [rejectFeedback, setRejectFeedback] = useState<string>('');
  const [markPostedModalOpen, setMarkPostedModalOpen] = useState<boolean>(false);
  const [postedUrl, setPostedUrl] = useState<string>('');
  const [platformContentId, setPlatformContentId] = useState<string>('');
  const [addLinkModalOpen, setAddLinkModalOpen] = useState<boolean>(false);
  const [addLinkUrl, setAddLinkUrl] = useState<string>('');
  const [addLinkId, setAddLinkId] = useState<string>('');

  // UI status
  const [copied, setCopied] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [versionWarning, setVersionWarning] = useState<string | null>(null);
  const [versionDropdownOpen, setVersionDropdownOpen] = useState<boolean>(false);

  const fetchDraftData = async (id: string) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const draftData = await apiClient.getDraft(id);
      setDraft(draftData);
      setEditContent(draftData.content);

      if (draftData.status === 'SUPERSEDED') {
        setVersionWarning('This draft changed. Reload to review the latest version.');
      } else {
        setVersionWarning(null);
      }

      // Fetch version history
      try {
        const versionList = await apiClient.getDraftVersions(id);
        setVersions(versionList);
      } catch {
        // Fallback version list
        setVersions([
          {
            version: draftData.version,
            status: draftData.status,
            created_by: draftData.created_by,
            created_at: draftData.created_at,
            is_approved: draftData.status === 'APPROVED',
            is_posted: draftData.status === 'POSTED',
          },
        ]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load draft details.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (effectiveDraftId) {
      fetchDraftData(effectiveDraftId);
    }
  }, [effectiveDraftId]);

  // Copy to clipboard with visual feedback
  const handleCopy = async () => {
    if (!draft?.content) return;
    try {
      await navigator.clipboard.writeText(draft.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard fallback
      setCopied(false);
    }
  };

  // 1. Approve Draft
  const handleApprove = async () => {
    if (!draft) return;
    setIsSubmitting(true);
    setError(null);
    setVersionWarning(null);

    try {
      if (approval) {
        await apiClient.submitApprovalDecision(approval.id, {
          item_id: draft.id,
          decision: 'APPROVED',
        });
      }
      setDraft((prev) => (prev ? { ...prev, status: 'APPROVED' } : null));
      if (onDecisionSubmitted) onDecisionSubmitted();
    } catch (err: unknown) {
      if (err instanceof ApiClientError && (err.code === 'STALE_APPROVAL' || err.code === 'STALE_VERSION')) {
        setVersionWarning('This draft changed. Reload to review the latest version.');
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to approve draft.';
        setError(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // 2. Reject Draft with Feedback
  const handleConfirmReject = async () => {
    if (!draft) return;
    const feedback = rejectFeedback.trim();
    if (!feedback) return;

    setIsSubmitting(true);
    setError(null);
    setVersionWarning(null);

    try {
      if (approval) {
        await apiClient.submitApprovalDecision(approval.id, {
          item_id: draft.id,
          decision: 'REJECTED',
          feedback_text: feedback,
        });
      }
      setDraft((prev) => (prev ? { ...prev, status: 'REJECTED' } : null));
      setRejectModalOpen(false);
      if (onDecisionSubmitted) onDecisionSubmitted();
    } catch (err: unknown) {
      if (err instanceof ApiClientError && (err.code === 'STALE_APPROVAL' || err.code === 'STALE_VERSION')) {
        setVersionWarning('This draft changed. Reload to review the latest version.');
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to reject draft.';
        setError(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // 3. Save Edits and Approve
  const handleSaveEditsAndApprove = async () => {
    if (!draft) return;
    const content = editContent.trim();
    if (!content) {
      setEditErrors(['Draft content cannot be empty.']);
      return;
    }

    // Run client-side deterministic quality check first (ADR-023, FR-15)
    const checkResult = checkDeterministicRequirements(content, draft.kind, draft.platform);
    if (!checkResult.passed) {
      setEditErrors(checkResult.issues);
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setEditErrors([]);
    setVersionWarning(null);

    try {
      if (approval && approval.status === 'PENDING') {
        const resp = await apiClient.submitApprovalDecision(approval.id, {
          item_id: draft.id,
          decision: 'EDITED',
          edited_content: content,
        });
        if (resp.resulting_item_id) {
          await fetchDraftData(resp.resulting_item_id);
        }
        setIsEditing(false);
        if (onDecisionSubmitted) onDecisionSubmitted();
      } else {
        // Outside approval: edit draft creates a new version
        const editResp = await apiClient.editDraft(draft.id, {
          content,
          expected_version: draft.version,
        });
        await fetchDraftData(editResp.draft_id);
        setIsEditing(false);
        if (onDraftUpdated && draft) {
          onDraftUpdated(draft);
        }
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.code === 'STALE_APPROVAL' || err.code === 'STALE_VERSION') {
          setVersionWarning('This draft changed. Reload to review the latest version.');
        } else if (err.code === 'CHECKS_FAILED') {
          const detailIssues = (err.details?.issues as string[]) || ['Draft failed deterministic checks.'];
          setEditErrors(detailIssues);
        } else {
          setError(err.message);
        }
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to save edited draft.';
        setError(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // 4. Mark as Posted (with optional link or platform ID)
  const handleConfirmMarkPosted = async () => {
    if (!draft) return;
    setIsSubmitting(true);
    setError(null);

    try {
      const resp = await apiClient.markDraftPosted(draft.id, {
        posted_url: postedUrl.trim() || undefined,
        platform_content_id: platformContentId.trim() || undefined,
      });

      setDraft((prev) =>
        prev
          ? {
              ...prev,
              status: 'POSTED',
              posted_ref: resp.posted_ref,
              posted_url: postedUrl.trim() || null,
              posted_platform_id: platformContentId.trim() || null,
            }
          : null
      );
      setMarkPostedModalOpen(false);
    } catch (err: unknown) {
      if (err instanceof ApiClientError && (err.code === 'STALE_VERSION' || err.code === 'NOT_APPROVED')) {
        setError(err.message);
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to mark draft as posted.';
        setError(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // 5. Add Link to an unlinked posted draft
  const handleConfirmAddLink = async () => {
    if (!draft) return;
    if (!addLinkUrl.trim() && !addLinkId.trim()) {
      setError('Please provide either a published URL or a Platform Content ID.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const updated = await apiClient.linkDraftPosted(draft.id, {
        posted_url: addLinkUrl.trim() || undefined,
        platform_content_id: addLinkId.trim() || undefined,
      });
      setDraft(updated);
      setAddLinkModalOpen(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to attach link to posted draft.';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-[#64748B]">
        <Loader2 className="w-8 h-8 animate-spin text-[#6366F1] mb-3" />
        <p className="text-sm">Loading draft and critic evaluation...</p>
      </div>
    );
  }

  if (error && !draft) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700">
        <div className="flex items-center gap-2 font-medium mb-1">
          <AlertCircle className="w-5 h-5 text-red-600" />
          <span>Error Loading Draft</span>
        </div>
        <p className="text-sm">{error}</p>
        {onBack && (
          <Button variant="outline" size="sm" className="mt-4" onClick={onBack}>
            Back
          </Button>
        )}
      </div>
    );
  }

  if (!draft) return null;

  const currentContent = isEditing ? editContent : draft.content;
  const charCount = currentContent.length;
  const wordCount = currentContent.trim() ? currentContent.trim().split(/\s+/).length : 0;
  const platformLimit = getPlatformLimit(draft.platform, draft.kind);
  const isOverLimit = platformLimit ? charCount > platformLimit.maxChars : false;

  // Critic stats
  const critic = draft.critic_evaluation;
  const reviewLimitReached = critic ? critic.review_number >= 3 : false;
  const hasOpenIssues = critic && !critic.passed;

  const getStatusBadge = () => {
    switch (draft.status) {
      case 'APPROVED':
        return <Badge variant="success">Approved</Badge>;
      case 'POSTED':
        if (draft.posted_ref === 'none' || (!draft.posted_url && !draft.posted_platform_id)) {
          return <Badge variant="warning">Posted (no link)</Badge>;
        }
        return <Badge variant="primary">Posted</Badge>;
      case 'REJECTED':
        return <Badge variant="error">Rejected</Badge>;
      case 'SUPERSEDED':
        return <Badge variant="neutral">Superseded</Badge>;
      case 'PENDING_APPROVAL':
      default:
        return <Badge variant="info">Pending Review</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Navigation & Version Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E2E8F0] pb-4">
        <div className="flex items-center gap-3">
          {onBack && (
            <button
              onClick={onBack}
              aria-label="Back to inbox"
              className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <div>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Badge variant="primary" size="sm">
                {draft.platform.toUpperCase()}
              </Badge>
              <Badge variant="neutral" size="sm">
                {draft.kind.replace('_', ' ').toUpperCase()}
              </Badge>
              {getStatusBadge()}
            </div>
            <h1 className="text-xl font-bold text-[#0F172A] flex items-center gap-2">
              <span>Version {draft.version}</span>
              <span className="text-xs font-normal text-[#64748B]">
                ({draft.created_by === 'creator' ? 'Creator Edited' : 'Model Generated'})
              </span>
            </h1>
          </div>
        </div>

        {/* Version Switcher Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setVersionDropdownOpen(!versionDropdownOpen)}
            className="inline-flex items-center gap-2 px-3 py-1.5 bg-white border border-[#E2E8F0] rounded-lg text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-xs cursor-pointer"
          >
            <span>Switch Version ({versions.length} available)</span>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          </button>

          {versionDropdownOpen && (
            <div className="absolute right-0 mt-2 w-56 bg-white border border-[#E2E8F0] rounded-xl shadow-lg z-20 py-1 overflow-hidden">
              <div className="px-3 py-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                Version History
              </div>
              {versions.map((ver) => (
                <button
                  key={ver.version}
                  onClick={() => {
                    setVersionDropdownOpen(false);
                    // If viewing an approval, warning that approval applies to version on screen
                    if (ver.version !== draft.version) {
                      // Reload draft for this version if separate ID, or inform user
                    }
                  }}
                  className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-slate-50 transition-colors ${
                    ver.version === draft.version ? 'bg-indigo-50/50 text-[#6366F1] font-semibold' : 'text-slate-700'
                  }`}
                >
                  <div className="flex flex-col">
                    <span>Version {ver.version}</span>
                    <span className="text-[10px] text-slate-400">By {ver.created_by}</span>
                  </div>
                  <Badge
                    size="sm"
                    variant={ver.status === 'APPROVED' ? 'success' : ver.status === 'POSTED' ? 'primary' : 'neutral'}
                  >
                    {ver.status}
                  </Badge>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Global Warnings & Approval Note */}
      <div className="space-y-2">
        <div className="px-3 py-2 bg-indigo-50/70 border border-indigo-100 rounded-lg text-xs text-indigo-800 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#6366F1] shrink-0" />
          <span>
            <strong>Approval Notice:</strong> Approval always applies to the version on screen.
          </span>
        </div>

        {versionWarning && (
          <div className="px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-center gap-2.5">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
            <div>
              <strong>Draft Outdated:</strong> {versionWarning}
            </div>
          </div>
        )}

        {/* Review limit reached banner (DESIGN 4.4) */}
        {reviewLimitReached && hasOpenIssues && (
          <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center gap-2.5">
            <ShieldAlert className="w-5 h-5 text-red-600 shrink-0" />
            <div>
              <strong>Review Limit Reached:</strong> This draft reached the maximum review iterations and still has open issues. Best candidate in lineage selected for review.
            </div>
          </div>
        )}

        {/* Posted (no link) Banner (DESIGN 4.4) */}
        {draft.status === 'POSTED' && draft.posted_ref === 'none' && (
          <div className="px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              <span>
                <strong>Posted (no link):</strong> Automated metrics are unavailable until you add a link.
              </span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAddLinkModalOpen(true)}
              leftIcon={<LinkIcon className="w-3.5 h-3.5" />}
            >
              Add link
            </Button>
          </div>
        )}
      </div>

      {/* Main Grid: Draft Panel + Critic Side Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Draft Content & Editor (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <Card className="p-5 relative shadow-xs border-[#E2E8F0]">
            {/* Panel Header */}
            <div className="flex items-center justify-between pb-3 border-b border-[#F1F5F9] mb-4">
              <div className="flex items-center gap-3">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Draft Content
                </span>
                {platformLimit && (
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      isOverLimit ? 'bg-red-50 text-red-600 font-semibold' : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {charCount} / {platformLimit.maxChars} chars
                  </span>
                )}
                <span className="text-xs text-slate-400">· {wordCount} words</span>
              </div>

              {!isEditing && draft.status !== 'POSTED' && (
                <button
                  type="button"
                  onClick={() => {
                    setIsEditing(true);
                    setEditErrors([]);
                  }}
                  className="inline-flex items-center gap-1.5 text-xs text-[#6366F1] hover:text-indigo-700 font-medium cursor-pointer"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  <span>Edit inline</span>
                </button>
              )}
            </div>

            {/* Read Mode */}
            {!isEditing && (
              <div className="space-y-4">
                <div className="p-4 bg-slate-50/70 border border-slate-100 rounded-lg text-sm text-[#0F172A] whitespace-pre-wrap font-sans leading-relaxed select-text">
                  {draft.content}
                </div>

                {/* Section Quality Indicators */}
                <div className="flex items-center gap-2 pt-2 border-t border-slate-100 text-xs text-slate-500 flex-wrap">
                  <span className="font-medium text-slate-600">Sections Detected:</span>
                  <span
                    className={`px-2 py-0.5 rounded-md ${
                      draft.content.toLowerCase().includes('hook') || draft.content.toLowerCase().includes('intro')
                        ? 'bg-green-50 text-green-700'
                        : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    Hook
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-md ${
                      draft.content.toLowerCase().includes('body') || draft.content.length > 80
                        ? 'bg-green-50 text-green-700'
                        : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    Body
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-md ${
                      draft.content.toLowerCase().includes('cta') ||
                      draft.content.toLowerCase().includes('subscribe') ||
                      draft.content.toLowerCase().includes('follow') ||
                      draft.content.toLowerCase().includes('comment')
                        ? 'bg-green-50 text-green-700'
                        : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    CTA
                  </span>
                </div>
              </div>
            )}

            {/* Edit Mode */}
            {isEditing && (
              <div className="space-y-3">
                {/* Warning when editing approved draft */}
                {draft.status === 'APPROVED' && (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                    <span>
                      <strong>Notice:</strong> Saving creates a new version that needs approval. The current approval will no longer apply.
                    </span>
                  </div>
                )}

                {editErrors.length > 0 && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 space-y-1">
                    <div className="flex items-center gap-1.5 font-semibold">
                      <AlertCircle className="w-4 h-4 text-red-600" />
                      <span>Draft checks failed:</span>
                    </div>
                    <ul className="list-disc pl-5 space-y-0.5">
                      {editErrors.map((err, idx) => (
                        <li key={idx}>{err}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <textarea
                  value={editContent}
                  onChange={(e) => {
                    setEditContent(e.target.value);
                    if (editErrors.length > 0) setEditErrors([]);
                  }}
                  rows={14}
                  className="w-full p-3.5 text-sm font-mono text-[#0F172A] bg-white border border-[#E2E8F0] rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-[#6366F1] transition-all"
                  placeholder="Enter draft content..."
                />

                <div className="flex items-center justify-between pt-2">
                  <div className="text-xs text-slate-500">
                    {charCount} characters · {wordCount} words
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setIsEditing(false);
                        setEditContent(draft.content);
                        setEditErrors([]);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      isLoading={isSubmitting}
                      onClick={handleSaveEditsAndApprove}
                    >
                      Save and approve
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </Card>

          {/* Action Bar */}
          <div className="flex items-center justify-between gap-3 pt-2">
            <div className="flex items-center gap-2">
              {/* Copy button available on approved and posted drafts (DESIGN 4.4) */}
              {(draft.status === 'APPROVED' || draft.status === 'POSTED') && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopy}
                  leftIcon={copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                >
                  {copied ? 'Copied!' : 'Copy'}
                </Button>
              )}

              {/* Mark as posted action available after approval (DESIGN 4.4) */}
              {draft.status === 'APPROVED' && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setMarkPostedModalOpen(true)}
                  leftIcon={<Share2 className="w-4 h-4" />}
                >
                  Mark as posted
                </Button>
              )}

              {/* Add Link action if posted without link */}
              {draft.status === 'POSTED' && draft.posted_ref === 'none' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setAddLinkModalOpen(true)}
                  leftIcon={<LinkIcon className="w-4 h-4" />}
                >
                  Add link
                </Button>
              )}

              {/* Direct link if posted with URL */}
              {draft.status === 'POSTED' && draft.posted_url && (
                <a
                  href={draft.posted_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-indigo-600 hover:text-indigo-800 bg-indigo-50 border border-indigo-100 rounded-lg font-medium"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>View Published Post</span>
                </a>
              )}
            </div>

            {/* Approval decision actions when pending approval */}
            {draft.status === 'PENDING_APPROVAL' && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRejectModalOpen(true)}
                  disabled={isSubmitting}
                  leftIcon={<XCircle className="w-4 h-4 text-red-500" />}
                >
                  Reject with feedback
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  isLoading={isSubmitting}
                  onClick={handleApprove}
                  leftIcon={<CheckCircle2 className="w-4 h-4" />}
                >
                  Approve
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Critic Panel (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <Card className="p-5 shadow-xs border-[#E2E8F0]">
            <div className="flex items-center justify-between pb-3 border-b border-[#F1F5F9] mb-4">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Critic Evaluation
                </span>
                {critic && (
                  <Badge variant={critic.passed ? 'success' : 'warning'} size="sm">
                    {critic.passed ? 'Passed Rubric' : 'Needs Polish'}
                  </Badge>
                )}
              </div>
              {critic && (
                <span className="text-xs text-slate-500 font-medium">
                  Review {critic.review_number} of 3
                </span>
              )}
            </div>

            {!critic && (
              <div className="text-center py-8 text-slate-400 text-xs">
                No automated Critic evaluation recorded for this version.
              </div>
            )}

            {critic && (
              <div className="space-y-4">
                {/* Overall Score */}
                <div className="flex items-center justify-between p-3.5 bg-slate-50 rounded-xl border border-slate-100">
                  <div>
                    <div className="text-xs text-slate-500">Overall Rubric Score</div>
                    <div className="text-2xl font-bold text-[#0F172A] tracking-tight">
                      {critic.score.toFixed(1)}{' '}
                      <span className="text-xs font-normal text-slate-400">/ 10</span>
                    </div>
                  </div>
                  <div
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                      critic.score >= 7.0 ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {critic.score >= 7.0 ? 'High Quality' : 'Adequate'}
                  </div>
                </div>

                {/* Rubric Breakdown */}
                {critic.rubric && Object.keys(critic.rubric).length > 0 && (
                  <div className="space-y-2.5">
                    <div className="text-xs font-semibold text-slate-700">Rubric Dimensions</div>
                    <div className="space-y-2">
                      {Object.entries(critic.rubric).map(([dim, val]) => (
                        <div key={dim} className="p-2.5 bg-white border border-slate-100 rounded-lg space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-medium text-slate-800 capitalize">{dim}</span>
                            <span className="font-semibold text-slate-700">{val.score} / 10</span>
                          </div>
                          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                val.score >= 8 ? 'bg-green-500' : val.score >= 6 ? 'bg-indigo-500' : 'bg-amber-500'
                              }`}
                              style={{ width: `${Math.min(100, val.score * 10)}%` }}
                            />
                          </div>
                          {val.notes && <p className="text-[11px] text-slate-500 mt-1">{val.notes}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Issues & Suggestions */}
                {critic.feedback && (
                  <div className="space-y-3 pt-2 border-t border-slate-100">
                    {critic.feedback.issues && critic.feedback.issues.length > 0 && (
                      <div className="space-y-1.5">
                        <div className="text-xs font-semibold text-red-600 flex items-center gap-1">
                          <AlertCircle className="w-3.5 h-3.5" />
                          <span>Identified Issues</span>
                        </div>
                        <ul className="text-xs text-slate-600 space-y-1 pl-4 list-disc">
                          {critic.feedback.issues.map((issue, idx) => (
                            <li key={idx}>{issue}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {critic.feedback.suggestions && critic.feedback.suggestions.length > 0 && (
                      <div className="space-y-1.5">
                        <div className="text-xs font-semibold text-indigo-600 flex items-center gap-1">
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Actionable Suggestions</span>
                        </div>
                        <ul className="text-xs text-slate-600 space-y-1 pl-4 list-disc">
                          {critic.feedback.suggestions.map((sug, idx) => (
                            <li key={idx}>{sug}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {critic.feedback.strengths && critic.feedback.strengths.length > 0 && (
                      <div className="space-y-1.5">
                        <div className="text-xs font-semibold text-green-600 flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Strengths</span>
                        </div>
                        <ul className="text-xs text-slate-600 space-y-1 pl-4 list-disc">
                          {critic.feedback.strengths.map((str, idx) => (
                            <li key={idx}>{str}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Reject Modal */}
      <Modal
        isOpen={rejectModalOpen}
        onClose={() => setRejectModalOpen(false)}
        title="Reject Draft"
        description="Provide feedback explaining why this draft requires revision."
      >
        <div className="space-y-4">
          <textarea
            value={rejectFeedback}
            onChange={(e) => setRejectFeedback(e.target.value)}
            rows={4}
            className="w-full p-3 text-sm text-[#0F172A] border border-[#E2E8F0] rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
            placeholder="Explain what needs to change (e.g. Tone is too formal, hook is too passive)..."
          />
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setRejectModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={!rejectFeedback.trim()}
              isLoading={isSubmitting}
              onClick={handleConfirmReject}
            >
              Reject draft
            </Button>
          </div>
        </div>
      </Modal>

      {/* Mark As Posted Modal (UI-05, DESIGN 4.4) */}
      <Modal
        isOpen={markPostedModalOpen}
        onClose={() => setMarkPostedModalOpen(false)}
        title="Mark as Posted"
        description="Record published URL or platform ID to enable audience performance tracking."
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Published URL (Optional)
            </label>
            <input
              type="url"
              value={postedUrl}
              onChange={(e) => setPostedUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=... or https://x.com/..."
              className="w-full p-2.5 text-xs text-[#0F172A] border border-[#E2E8F0] rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-[#6366F1]"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Platform Content ID (Optional)
            </label>
            <input
              type="text"
              value={platformContentId}
              onChange={(e) => setPlatformContentId(e.target.value)}
              placeholder="e.g. Video ID dQw4w9WgXcQ"
              className="w-full p-2.5 text-xs text-[#0F172A] border border-[#E2E8F0] rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-[#6366F1]"
            />
          </div>

          <p className="text-[11px] text-slate-500 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
            If posted without a link, automated metrics will be unavailable until you add one later.
          </p>

          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setMarkPostedModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={isSubmitting}
              onClick={handleConfirmMarkPosted}
            >
              Confirm mark as posted
            </Button>
          </div>
        </div>
      </Modal>

      {/* Add Link Dialog for Unlinked Posted Draft (UI-05, DESIGN 4.4) */}
      <Modal
        isOpen={addLinkModalOpen}
        onClose={() => setAddLinkModalOpen(false)}
        title="Add Platform Link"
        description="Attach a published URL or platform content ID to enable metrics tracking."
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Published Post URL
            </label>
            <input
              type="url"
              value={addLinkUrl}
              onChange={(e) => setAddLinkUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=..."
              className="w-full p-2.5 text-xs text-[#0F172A] border border-[#E2E8F0] rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-[#6366F1]"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Platform Content ID
            </label>
            <input
              type="text"
              value={addLinkId}
              onChange={(e) => setAddLinkId(e.target.value)}
              placeholder="e.g. YouTube Video ID"
              className="w-full p-2.5 text-xs text-[#0F172A] border border-[#E2E8F0] rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-[#6366F1]"
            />
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setAddLinkModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!addLinkUrl.trim() && !addLinkId.trim()}
              isLoading={isSubmitting}
              onClick={handleConfirmAddLink}
            >
              Attach Link
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
