import React, { useState, useEffect, useCallback } from 'react';
import {
  MessageSquare,
  TrendingUp,
  Brain,
  RefreshCw,
  AlertCircle,
  ThumbsUp,
  Clock,
  History,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  CheckCircle,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import {
  CommentInsightResponse,
  AnalystFindingResponse,
  StrategyEntryResponse,
} from '../../types';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';

export type InsightsTab = 'comments' | 'findings' | 'strategy';

export const InsightsScreen: React.FC = () => {
  const [activeTab, setActiveTab] = useState<InsightsTab>('comments');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Data states
  const [commentInsights, setCommentInsights] = useState<CommentInsightResponse[]>([]);
  const [findings, setFindings] = useState<AnalystFindingResponse[]>([]);
  const [strategyEntries, setStrategyEntries] = useState<StrategyEntryResponse[]>([]);
  const [includeStrategyHistory, setIncludeStrategyHistory] = useState<boolean>(false);

  // Filter & expand states
  const [confidenceFilter, setConfidenceFilter] = useState<'all' | 'high' | 'moderate' | 'low'>('all');
  const [expandedThemes, setExpandedThemes] = useState<Record<string, boolean>>({});
  const [expandedFindings, setExpandedFindings] = useState<Record<string, boolean>>({});

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [commentsData, findingsData, strategyData] = await Promise.all([
        apiClient.getCommentInsights(),
        apiClient.getFindings(),
        apiClient.getStrategy({
          include: includeStrategyHistory ? 'history' : undefined,
        }),
      ]);

      setCommentInsights(commentsData);
      setFindings(findingsData);
      setStrategyEntries(strategyData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch insights data.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [includeStrategyHistory]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const toggleThemeExpanded = (themeId: string) => {
    setExpandedThemes((prev) => ({
      ...prev,
      [themeId]: !prev[themeId],
    }));
  };

  const toggleFindingExpanded = (findingId: string) => {
    setExpandedFindings((prev) => ({
      ...prev,
      [findingId]: !prev[findingId],
    }));
  };

  const filteredFindings = findings.filter((f) => {
    if (confidenceFilter === 'all') return true;
    return f.confidence === confidenceFilter;
  });

  const getConfidenceBadgeVariant = (confidence: 'low' | 'moderate' | 'high') => {
    switch (confidence) {
      case 'high':
        return 'success';
      case 'moderate':
        return 'warning';
      case 'low':
      default:
        return 'neutral';
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#0F172A]">Insights & Strategy Memory</h1>
          <p className="text-sm text-[#64748B] mt-1">
            Audience themes, post-mortem findings, and empirical strategy rules.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={loadData}
            disabled={loading}
            leftIcon={<RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="flex items-center gap-4 py-4">
          <div className="w-12 h-12 rounded-lg bg-indigo-50 text-[#6366F1] flex items-center justify-center shrink-0">
            <MessageSquare className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-medium text-[#64748B] uppercase tracking-wider">Comment Themes</p>
            <p className="text-2xl font-bold text-[#0F172A]">{commentInsights.length}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-4 py-4">
          <div className="w-12 h-12 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
            <TrendingUp className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-medium text-[#64748B] uppercase tracking-wider">Analyst Findings</p>
            <p className="text-2xl font-bold text-[#0F172A]">{findings.length}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-4 py-4">
          <div className="w-12 h-12 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center shrink-0">
            <Brain className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-medium text-[#64748B] uppercase tracking-wider">Strategy Rules</p>
            <p className="text-2xl font-bold text-[#0F172A]">
              {strategyEntries.filter((s) => s.status === 'active').length}
            </p>
          </div>
        </Card>
      </div>

      {/* Main Tab Navigation */}
      <div className="border-b border-[#E2E8F0]">
        <div className="flex gap-6 overflow-x-auto" role="tablist">
          <button
            role="tab"
            aria-selected={activeTab === 'comments'}
            onClick={() => setActiveTab('comments')}
            className={`pb-3 text-sm font-medium flex items-center gap-2 border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'comments'
                ? 'border-[#6366F1] text-[#6366F1]'
                : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            Comment Themes
            <span className="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-slate-100 text-[#64748B]">
              {commentInsights.length}
            </span>
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'findings'}
            onClick={() => setActiveTab('findings')}
            className={`pb-3 text-sm font-medium flex items-center gap-2 border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'findings'
                ? 'border-[#6366F1] text-[#6366F1]'
                : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            Analyst Findings
            <span className="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-slate-100 text-[#64748B]">
              {findings.length}
            </span>
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'strategy'}
            onClick={() => setActiveTab('strategy')}
            className={`pb-3 text-sm font-medium flex items-center gap-2 border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'strategy'
                ? 'border-[#6366F1] text-[#6366F1]'
                : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
            }`}
          >
            <Brain className="w-4 h-4" />
            Strategy Memory
            <span className="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-slate-100 text-[#64748B]">
              {strategyEntries.length}
            </span>
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <Card className="py-12 flex flex-col items-center justify-center text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-[#6366F1] mb-3" />
          <p className="text-sm text-[#64748B]">Loading audience insights and strategy memory...</p>
        </Card>
      )}

      {/* Error state */}
      {!loading && error && (
        <Card className="p-6 border-red-200 bg-red-50 text-red-700 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <p className="text-sm font-medium">{error}</p>
          </div>
          <Button variant="secondary" size="sm" onClick={loadData}>
            Try Again
          </Button>
        </Card>
      )}

      {/* Tab: Comment Themes */}
      {!loading && !error && activeTab === 'comments' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-[#64748B]">
              Filtered by channel ownership rule (ADR-032). Comments older than 90 days have text cleared per retention policy (ADR-033).
            </p>
          </div>

          {commentInsights.length === 0 ? (
            <Card className="py-12 text-center">
              <MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-semibold text-[#0F172A]">No Comment Themes Found</h3>
              <p className="text-sm text-[#64748B] max-w-md mx-auto mt-1">
                Comment themes are extracted during research runs for your connected YouTube channel.
                Verify your channel in Settings and run audience analysis.
              </p>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {commentInsights.map((theme) => {
                const isExpanded = expandedThemes[theme.id] ?? true;
                const coveragePct =
                  theme.coverage_total > 0
                    ? Math.round((theme.coverage_analyzed / theme.coverage_total) * 100)
                    : 100;

                return (
                  <Card key={theme.id} className="p-5 hover:border-slate-300 transition-colors">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="text-base font-semibold text-[#0F172A]">{theme.theme_label}</h3>
                          <Badge variant="primary" size="sm">
                            {theme.comment_count} comments
                          </Badge>
                          <Badge variant="neutral" size="sm">
                            Coverage: {coveragePct}% ({theme.coverage_analyzed}/{theme.coverage_total})
                          </Badge>
                        </div>
                        <p className="text-xs text-[#64748B] mt-1">
                          Identified {new Date(theme.created_at).toLocaleDateString()}
                        </p>
                      </div>

                      {theme.examples.length > 0 && (
                        <button
                          onClick={() => toggleThemeExpanded(theme.id)}
                          className="flex items-center gap-1 text-xs font-medium text-[#6366F1] hover:text-indigo-800 self-start sm:self-center"
                        >
                          {isExpanded ? (
                            <>
                              Hide Examples <ChevronUp className="w-3.5 h-3.5" />
                            </>
                          ) : (
                            <>
                              View Examples ({theme.examples.length}) <ChevronDown className="w-3.5 h-3.5" />
                            </>
                          )}
                        </button>
                      )}
                    </div>

                    {/* Example comments */}
                    {isExpanded && theme.examples.length > 0 && (
                      <div className="mt-4 pt-4 border-t border-slate-100 space-y-2.5">
                        <p className="text-xs font-medium text-[#64748B] uppercase tracking-wider">
                          Sample Comments
                        </p>
                        <div className="space-y-2">
                          {theme.examples.map((ex, idx) => (
                            <div
                              key={ex.comment_id || idx}
                              className={`p-3 rounded-lg text-sm border ${
                                ex.available && ex.text
                                  ? 'bg-[#F8FAFC] border-slate-200 text-[#0F172A]'
                                  : 'bg-amber-50/50 border-amber-200 text-amber-800 italic'
                              }`}
                            >
                              {ex.available && ex.text ? (
                                <div className="space-y-1.5">
                                  <p className="whitespace-pre-wrap leading-relaxed">{ex.text}</p>
                                  <div className="flex items-center gap-3 text-xs text-[#64748B]">
                                    {ex.like_count > 0 && (
                                      <span className="flex items-center gap-1 font-medium">
                                        <ThumbsUp className="w-3 h-3" /> {ex.like_count}
                                      </span>
                                    )}
                                    <span className="flex items-center gap-1">
                                      <Clock className="w-3 h-3" />{' '}
                                      {new Date(ex.published_at).toLocaleDateString()}
                                    </span>
                                  </div>
                                </div>
                              ) : (
                                <div className="flex items-center gap-2 text-xs">
                                  <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0" />
                                  <span>Example no longer available (cleared after 90 days retention)</span>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab: Analyst Findings */}
      {!loading && !error && activeTab === 'findings' && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p className="text-xs text-[#64748B]">
              Empirical insights extracted by the ReAct Post-Mortem Analyst from linked posted drafts.
            </p>
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#64748B]">Confidence:</span>
              {(['all', 'high', 'moderate', 'low'] as const).map((conf) => (
                <button
                  key={conf}
                  onClick={() => setConfidenceFilter(conf)}
                  className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors capitalize ${
                    confidenceFilter === conf
                      ? 'bg-[#6366F1] text-white'
                      : 'bg-slate-100 text-[#64748B] hover:bg-slate-200'
                  }`}
                >
                  {conf}
                </button>
              ))}
            </div>
          </div>

          {filteredFindings.length === 0 ? (
            <Card className="py-12 text-center">
              <TrendingUp className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-semibold text-[#0F172A]">No Analyst Findings</h3>
              <p className="text-sm text-[#64748B] max-w-md mx-auto mt-1">
                Post-mortem findings are generated after analyzing performance on posted drafts.
                Mark approved drafts as posted and provide their platform link to begin analysis.
              </p>
            </Card>
          ) : (
            <div className="space-y-4">
              {filteredFindings.map((finding) => {
                const isExpanded = expandedFindings[finding.id] ?? false;
                const hasEvidence =
                  finding.evidence && Object.keys(finding.evidence).length > 0;

                return (
                  <Card key={finding.id} className="p-5 space-y-3.5">
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge
                            variant={getConfidenceBadgeVariant(finding.confidence)}
                            size="sm"
                            className="capitalize"
                          >
                            {finding.confidence} confidence
                          </Badge>
                          <Badge variant="neutral" size="sm">
                            Sample: {finding.sample_size} {finding.sample_size === 1 ? 'post' : 'posts'}
                          </Badge>
                          {finding.draft_id && (
                            <Badge variant="info" size="sm">
                              Draft {finding.draft_id.slice(0, 8)}
                            </Badge>
                          )}
                        </div>
                        <h3 className="text-base font-semibold text-[#0F172A] pt-1">
                          {finding.finding}
                        </h3>
                      </div>
                      <span className="text-xs text-[#64748B] shrink-0">
                        {new Date(finding.created_at).toLocaleDateString()}
                      </span>
                    </div>

                    {/* Recommendation box */}
                    <div className="bg-emerald-50/70 border border-emerald-200 rounded-lg p-3 text-sm text-emerald-900 flex items-start gap-2.5">
                      <CheckCircle className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                      <div>
                        <span className="font-semibold text-emerald-800">Recommendation: </span>
                        <span>{finding.recommendation}</span>
                      </div>
                    </div>

                    {/* Evidence expandable */}
                    {hasEvidence && (
                      <div>
                        <button
                          onClick={() => toggleFindingExpanded(finding.id)}
                          className="flex items-center gap-1 text-xs font-medium text-[#6366F1] hover:text-indigo-800"
                        >
                          {isExpanded ? (
                            <>
                              Hide Evidence Metrics <ChevronUp className="w-3 h-3" />
                            </>
                          ) : (
                            <>
                              View Evidence Metrics <ChevronDown className="w-3 h-3" />
                            </>
                          )}
                        </button>
                        {isExpanded && (
                          <div className="mt-2.5 bg-[#F8FAFC] border border-slate-200 rounded-lg p-3">
                            <pre className="text-xs text-[#0F172A] overflow-x-auto font-mono">
                              {JSON.stringify(finding.evidence, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab: Strategy Memory */}
      {!loading && !error && activeTab === 'strategy' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p className="text-xs text-[#64748B]">
              Persistent strategy rules that guide content planning. Each rule retains full revision lineage.
            </p>
            <label className="flex items-center gap-2 text-xs text-[#0F172A] cursor-pointer self-start sm:self-center">
              <input
                type="checkbox"
                checked={includeStrategyHistory}
                onChange={(e) => setIncludeStrategyHistory(e.target.checked)}
                className="w-4 h-4 rounded text-[#6366F1] border-slate-300 focus:ring-[#6366F1]"
              />
              <span className="flex items-center gap-1 font-medium">
                <History className="w-3.5 h-3.5 text-[#64748B]" /> Include Superseded History
              </span>
            </label>
          </div>

          {strategyEntries.length === 0 ? (
            <Card className="py-12 text-center">
              <Brain className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-semibold text-[#0F172A]">No Strategy Rules Recorded</h3>
              <p className="text-sm text-[#64748B] max-w-md mx-auto mt-1">
                Strategy rules adapt automatically when the Strategist incorporates Analyst findings.
                Future content plans will strictly honor these strategy constraints.
              </p>
            </Card>
          ) : (
            <div className="space-y-4">
              {strategyEntries.map((entry) => {
                const isActive = entry.status === 'active';

                return (
                  <Card
                    key={entry.id}
                    className={`p-5 space-y-3 transition-colors ${
                      isActive ? 'border-slate-200' : 'border-slate-200/60 bg-slate-50/50 opacity-80'
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold font-mono text-[#0F172A] bg-slate-100 px-2.5 py-1 rounded-md">
                          {entry.key}
                        </span>
                        <Badge variant={isActive ? 'success' : 'neutral'} size="sm">
                          {isActive ? 'Active' : 'Superseded'}
                        </Badge>
                        {entry.supporting_finding_ids.length > 0 && (
                          <Badge variant="info" size="sm">
                            {entry.supporting_finding_ids.length} supporting finding(s)
                          </Badge>
                        )}
                      </div>
                      <span className="text-xs text-[#64748B] shrink-0">
                        {new Date(entry.created_at).toLocaleDateString()}
                      </span>
                    </div>

                    {/* Value representation */}
                    <div className="bg-[#F8FAFC] border border-slate-200 rounded-lg p-3 text-xs font-mono text-[#0F172A] overflow-x-auto">
                      {typeof entry.value === 'object' && entry.value !== null
                        ? JSON.stringify(entry.value, null, 2)
                        : String(entry.value)}
                    </div>

                    {/* Reason */}
                    <div className="text-sm text-[#334155] space-y-1">
                      <p className="text-xs font-semibold text-[#64748B] uppercase tracking-wider">
                        Rationale
                      </p>
                      <p className="leading-relaxed">{entry.reason}</p>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
