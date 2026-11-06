import React, { useState, useEffect } from 'react';
import {
  FileText,
  Copy,
  Check,
  Share2,
  Link as LinkIcon,
  Filter,
  Loader2,
  ChevronRight,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { DraftResponse } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { DraftReview } from './DraftReview';
import { Modal } from '../common/Modal';

type LibraryTab = 'ready' | 'posted' | 'all';

export const DraftsLibrary: React.FC = () => {
  const [activeTab, setActiveTab] = useState<LibraryTab>('ready');
  const [drafts, setDrafts] = useState<DraftResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [platformFilter, setPlatformFilter] = useState<string>('all');
  const [kindFilter, setKindFilter] = useState<string>('all');

  // Selected draft for detail view
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);

  // Quick action states
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [markPostedModalDraft, setMarkPostedModalDraft] = useState<DraftResponse | null>(null);
  const [postedUrl, setPostedUrl] = useState<string>('');
  const [platformContentId, setPlatformContentId] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const fetchDrafts = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: { status?: string; platform?: string; kind?: string; is_latest?: boolean } = {};
      if (platformFilter !== 'all') params.platform = platformFilter;
      if (kindFilter !== 'all') params.kind = kindFilter;

      if (activeTab === 'ready') {
        params.status = 'APPROVED';
        params.is_latest = true;
      } else if (activeTab === 'posted') {
        params.status = 'POSTED';
      }

      const data = await apiClient.listDrafts(params);
      setDrafts(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch library drafts.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDrafts();
  }, [activeTab, platformFilter, kindFilter]);

  const handleCopy = async (draft: DraftResponse) => {
    try {
      await navigator.clipboard.writeText(draft.content);
      setCopiedId(draft.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      setCopiedId(null);
    }
  };

  const handleConfirmMarkPosted = async () => {
    if (!markPostedModalDraft) return;
    setIsSubmitting(true);
    try {
      await apiClient.markDraftPosted(markPostedModalDraft.id, {
        posted_url: postedUrl.trim() || undefined,
        platform_content_id: platformContentId.trim() || undefined,
      });
      setMarkPostedModalDraft(null);
      setPostedUrl('');
      setPlatformContentId('');
      fetchDrafts();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to mark draft as posted.';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (selectedDraftId) {
    return (
      <DraftReview
        draftId={selectedDraftId}
        onBack={() => {
          setSelectedDraftId(null);
          fetchDrafts();
        }}
        onDraftUpdated={() => {
          fetchDrafts();
        }}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[#0F172A] tracking-tight">
            Drafts Library
          </h1>
          <p className="text-sm text-[#64748B] mt-1">
            Manage approved content ready to publish, track posted versions, and inspect past iterations.
          </p>
        </div>
      </div>

      {/* Tabs & Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E2E8F0] pb-3">
        {/* Tabs */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('ready')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
              activeTab === 'ready'
                ? 'bg-indigo-50 text-[#6366F1] font-semibold'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            Ready to post
          </button>
          <button
            onClick={() => setActiveTab('posted')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
              activeTab === 'posted'
                ? 'bg-indigo-50 text-[#6366F1] font-semibold'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            Posted
          </button>
          <button
            onClick={() => setActiveTab('all')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
              activeTab === 'all'
                ? 'bg-indigo-50 text-[#6366F1] font-semibold'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            All drafts
          </button>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <Filter className="w-3.5 h-3.5" />
            <span>Platform:</span>
          </div>
          <select
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            className="text-xs border border-[#E2E8F0] rounded-lg px-2 py-1 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
          >
            <option value="all">All platforms</option>
            <option value="youtube">YouTube</option>
            <option value="instagram">Instagram</option>
            <option value="linkedin">LinkedIn</option>
            <option value="x">X / Twitter</option>
          </select>

          <div className="flex items-center gap-1.5 text-xs text-slate-500 ml-2">
            <span>Kind:</span>
          </div>
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            className="text-xs border border-[#E2E8F0] rounded-lg px-2 py-1 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
          >
            <option value="all">All kinds</option>
            <option value="script">Script</option>
            <option value="title">Title</option>
            <option value="description">Description</option>
            <option value="community_post">Community Post</option>
            <option value="caption">Caption</option>
            <option value="linkedin_post">LinkedIn Post</option>
            <option value="x_thread">X Thread</option>
          </select>
        </div>
      </div>

      {/* Content Area */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 text-[#64748B]">
          <Loader2 className="w-8 h-8 animate-spin text-[#6366F1] mb-3" />
          <p className="text-sm">Loading drafts library...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          {error}
        </div>
      ) : drafts.length === 0 ? (
        <div className="text-center py-16 bg-white border border-[#E2E8F0] rounded-xl space-y-3">
          <div className="w-12 h-12 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mx-auto">
            <FileText className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-semibold text-[#0F172A]">No drafts found</h3>
          <p className="text-xs text-[#64748B] max-w-sm mx-auto">
            {activeTab === 'ready'
              ? 'There are no approved drafts ready to post yet. Complete approvals to populate this tab.'
              : activeTab === 'posted'
              ? 'No drafts have been marked as posted yet.'
              : 'No drafts match the selected filter criteria.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {drafts.map((draft) => {
            const isPostedNoLink =
              draft.status === 'POSTED' &&
              (draft.posted_ref === 'none' || (!draft.posted_url && !draft.posted_platform_id));

            return (
              <Card
                key={draft.id}
                className="p-4 hover:border-slate-300 transition-colors cursor-pointer group shadow-xs"
                onClick={() => setSelectedDraftId(draft.id)}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  {/* Left: Metadata & Preview */}
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="primary" size="sm">
                        {draft.platform.toUpperCase()}
                      </Badge>
                      <Badge variant="neutral" size="sm">
                        {draft.kind.replace('_', ' ').toUpperCase()}
                      </Badge>
                      <span className="text-xs text-slate-400 font-medium">v{draft.version}</span>
                      {draft.status === 'APPROVED' && <Badge variant="success" size="sm">Approved</Badge>}
                      {isPostedNoLink ? (
                        <Badge variant="warning" size="sm">Posted (no link)</Badge>
                      ) : draft.status === 'POSTED' ? (
                        <Badge variant="primary" size="sm">Posted</Badge>
                      ) : draft.status === 'PENDING_APPROVAL' ? (
                        <Badge variant="info" size="sm">Pending Review</Badge>
                      ) : null}
                    </div>

                    <p className="text-sm text-slate-700 line-clamp-2 font-mono leading-relaxed bg-slate-50 p-2 rounded-md">
                      {draft.content}
                    </p>

                    {draft.posted_url && (
                      <div className="flex items-center gap-1 text-[11px] text-indigo-600 truncate">
                        <LinkIcon className="w-3 h-3" />
                        <span className="truncate">{draft.posted_url}</span>
                      </div>
                    )}
                  </div>

                  {/* Right: Quick Actions */}
                  <div
                    className="flex items-center gap-2 shrink-0 sm:self-center"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleCopy(draft)}
                      leftIcon={
                        copiedId === draft.id ? (
                          <Check className="w-3.5 h-3.5 text-green-600" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )
                      }
                    >
                      {copiedId === draft.id ? 'Copied' : 'Copy'}
                    </Button>

                    {draft.status === 'APPROVED' && (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => setMarkPostedModalDraft(draft)}
                        leftIcon={<Share2 className="w-3.5 h-3.5" />}
                      >
                        Mark as posted
                      </Button>
                    )}

                    <button
                      onClick={() => setSelectedDraftId(draft.id)}
                      className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg group-hover:translate-x-0.5 transition-transform cursor-pointer"
                      title="Open draft review"
                    >
                      <ChevronRight className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Mark Posted Modal */}
      <Modal
        isOpen={!!markPostedModalDraft}
        onClose={() => setMarkPostedModalDraft(null)}
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
              placeholder="https://youtube.com/watch?v=..."
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
              placeholder="e.g. YouTube Video ID"
              className="w-full p-2.5 text-xs text-[#0F172A] border border-[#E2E8F0] rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-[#6366F1]"
            />
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setMarkPostedModalDraft(null)}>
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
    </div>
  );
};
