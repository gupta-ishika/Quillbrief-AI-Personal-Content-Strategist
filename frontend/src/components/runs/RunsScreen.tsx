import React, { useState, useEffect, useCallback } from 'react';
import {
  History,
  RefreshCw,
  Clock,
  Coins,
  Bot,
  Code2,
  AlertTriangle,
  Play,
  StopCircle,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  ListOrdered,
  Layers,
  ChevronRight,
  ExternalLink,
  ShieldAlert,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import {
  RunResponse,
  RoutingLogItem,
  RunStatus,
  TaskResponse,
} from '../../types';
import { Button } from '../common/Button';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { Modal } from '../common/Modal';

export interface RunsScreenProps {
  onNavigateToApprovals?: (approvalId?: string) => void;
  initialRunId?: string | null;
}

const STATUS_VARIANTS: Record<
  RunStatus,
  'success' | 'warning' | 'error' | 'info' | 'neutral'
> = {
  COMPLETED: 'success',
  RUNNING: 'info',
  PENDING: 'info',
  WAITING_APPROVAL: 'warning',
  INTERRUPTED: 'warning',
  STOPPED: 'neutral',
  FAILED: 'error',
};

const TASK_STATUS_VARIANTS: Record<
  string,
  'success' | 'warning' | 'error' | 'info' | 'neutral'
> = {
  DONE: 'success',
  TODO: 'neutral',
  SKIPPED: 'warning',
  FAILED: 'error',
};

export const RunsScreen: React.FC<RunsScreenProps> = ({
  onNavigateToApprovals,
  initialRunId = null,
}) => {
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initialRunId);
  const [selectedRun, setSelectedRun] = useState<RunResponse | null>(null);
  const [routingLogs, setRoutingLogs] = useState<RoutingLogItem[]>([]);
  const [isLoadingRuns, setIsLoadingRuns] = useState<boolean>(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [typeFilter, setTypeFilter] = useState<string>('ALL');
  const [activeTab, setActiveTab] = useState<'timeline' | 'tasks'>('timeline');

  // Cancel & Resume modal/state
  const [isCancelModalOpen, setIsCancelModalOpen] = useState<boolean>(false);
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [isResuming, setIsResuming] = useState<boolean>(false);

  // 1. Fetch runs list
  const fetchRuns = useCallback(async () => {
    setIsLoadingRuns(true);
    setError(null);
    try {
      const statusParam = statusFilter !== 'ALL' ? statusFilter : undefined;
      const typeParam = typeFilter !== 'ALL' ? typeFilter : undefined;
      const data = await apiClient.listRuns(statusParam, typeParam);
      setRuns(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch runs';
      setError(msg);
    } finally {
      setIsLoadingRuns(false);
    }
  }, [statusFilter, typeFilter]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // 2. Fetch run details and routing logs
  const fetchRunDetail = useCallback(async (runId: string) => {
    setIsLoadingDetail(true);
    try {
      const [runData, logs] = await Promise.all([
        apiClient.getRun(runId),
        apiClient.getRunRoutingLog(runId),
      ]);
      setSelectedRun(runData);
      setRoutingLogs(logs);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch run details';
      setError(msg);
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      fetchRunDetail(selectedRunId);
    } else {
      setSelectedRun(null);
      setRoutingLogs([]);
    }
  }, [selectedRunId, fetchRunDetail]);

  // 3. Polling active run if running
  useEffect(() => {
    if (!selectedRunId || !selectedRun) return;
    const isRunning = ['RUNNING', 'PENDING'].includes(selectedRun.status);
    if (!isRunning) return;

    const intervalId = window.setInterval(async () => {
      try {
        const [updatedRun, updatedLogs] = await Promise.all([
          apiClient.getRun(selectedRunId),
          apiClient.getRunRoutingLog(selectedRunId),
        ]);
        setSelectedRun(updatedRun);
        setRoutingLogs(updatedLogs);
      } catch {
        // silent polling catch
      }
    }, 3000);

    return () => clearInterval(intervalId);
  }, [selectedRunId, selectedRun]);

  // Cancel run handler
  const handleCancelRun = async () => {
    if (!selectedRun) return;
    setIsCancelling(true);
    try {
      await apiClient.cancelRun(selectedRun.id);
      setIsCancelModalOpen(false);
      await fetchRunDetail(selectedRun.id);
      await fetchRuns();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to cancel run';
      setError(msg);
    } finally {
      setIsCancelling(false);
    }
  };

  // Resume run handler
  const handleResumeRun = async () => {
    if (!selectedRun) return;
    setIsResuming(true);
    try {
      await apiClient.resumeRun(selectedRun.id);
      await fetchRunDetail(selectedRun.id);
      await fetchRuns();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to resume run';
      setError(msg);
    } finally {
      setIsResuming(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <History className="w-6 h-6 text-[#6366F1]" />
            <h1 className="text-2xl font-bold text-[#0F172A]">Execution Runs</h1>
          </div>
          <p className="text-sm text-[#64748B] mt-1">
            Supervisor routing history, execution tasks, and token usage timelines.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {selectedRun && (
            <Button
              variant="outline"
              size="sm"
              leftIcon={<ArrowLeft className="w-4 h-4" />}
              onClick={() => setSelectedRunId(null)}
            >
              All Runs
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            leftIcon={<RefreshCw className={`w-4 h-4 ${isLoadingRuns || isLoadingDetail ? 'animate-spin' : ''}`} />}
            onClick={() => {
              if (selectedRunId) {
                fetchRunDetail(selectedRunId);
              }
              fetchRuns();
            }}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div
          role="alert"
          className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-[#DC2626] flex items-center justify-between"
        >
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={() => setError(null)}>
            Dismiss
          </Button>
        </div>
      )}

      {/* RUN DETAIL VIEW */}
      {selectedRun ? (
        <div className="space-y-6">
          {/* Run Summary Card */}
          <Card className="p-6">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-100 pb-5">
              <div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 className="text-lg font-bold text-[#0F172A]">
                    Run <span className="font-mono text-sm text-[#64748B]">{selectedRun.id.slice(0, 8)}...</span>
                  </h2>
                  <Badge variant={STATUS_VARIANTS[selectedRun.status]}>
                    {selectedRun.status}
                  </Badge>
                  <Badge variant="primary" className="uppercase text-[10px]">
                    {selectedRun.depth_level}
                  </Badge>
                  <Badge variant="neutral" className="capitalize text-[10px]">
                    {selectedRun.run_type.replace(/_/g, ' ')}
                  </Badge>
                  {selectedRun.degraded && (
                    <Badge variant="warning" className="flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      Degraded
                    </Badge>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-4 text-xs text-[#64748B] mt-2">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" />
                    Created: {new Date(selectedRun.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  {selectedRun.finished_at && (
                    <span>
                      Finished: {new Date(selectedRun.finished_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2.5">
                {selectedRun.status === 'RUNNING' && (
                  <Button
                    variant="destructive"
                    size="sm"
                    leftIcon={<StopCircle className="w-4 h-4" />}
                    onClick={() => setIsCancelModalOpen(true)}
                  >
                    Cancel Run
                  </Button>
                )}
                {selectedRun.status === 'INTERRUPTED' && (
                  <>
                    <Button
                      variant="primary"
                      size="sm"
                      isLoading={isResuming}
                      leftIcon={<Play className="w-4 h-4" />}
                      onClick={handleResumeRun}
                    >
                      Resume Run
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setIsCancelModalOpen(true)}
                    >
                      Cancel Run
                    </Button>
                  </>
                )}
                {selectedRun.status === 'WAITING_APPROVAL' && onNavigateToApprovals && (
                  <Button
                    variant="primary"
                    size="sm"
                    rightIcon={<ExternalLink className="w-4 h-4" />}
                    onClick={() => onNavigateToApprovals(selectedRun.pending_approval_id || undefined)}
                  >
                    Review Approval
                  </Button>
                )}
              </div>
            </div>

            {/* Metrics Row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-5">
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
                <p className="text-xs text-[#64748B]">Total Steps</p>
                <p className="text-lg font-bold text-[#0F172A] mt-0.5">{selectedRun.step_count}</p>
              </div>
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
                <p className="text-xs text-[#64748B]">Tokens Consumed</p>
                <p className="text-lg font-bold text-[#0F172A] mt-0.5 flex items-center gap-1">
                  <Coins className="w-4 h-4 text-[#D97706]" />
                  {selectedRun.tokens_used.toLocaleString()}
                </p>
              </div>
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
                <p className="text-xs text-[#64748B]">Tasks Completed</p>
                <p className="text-lg font-bold text-[#0F172A] mt-0.5">
                  {selectedRun.tasks ? selectedRun.tasks.filter((t) => t.status === 'DONE').length : 0} of{' '}
                  {selectedRun.tasks ? selectedRun.tasks.length : 0}
                </p>
              </div>
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-100">
                <p className="text-xs text-[#64748B]">Current Node</p>
                <p className="text-lg font-bold text-[#0F172A] mt-0.5 capitalize">
                  {selectedRun.current_node ? selectedRun.current_node.replace(/_/g, ' ') : 'Idle'}
                </p>
              </div>
            </div>

            {/* Degraded Notice Banner (DESIGN 4.8) */}
            {selectedRun.degraded && (
              <div
                role="region"
                aria-label="Degraded Run Notice"
                className="mt-5 p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-[#B45309]"
              >
                <div className="flex items-start gap-2.5">
                  <AlertTriangle className="w-5 h-5 text-[#D97706] shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-[#92400E]">
                      Degraded Run Notice
                    </p>
                    <p className="mt-0.5 text-xs text-[#B45309]">
                      Some steps used default choices or missing tools, so this result may be incomplete.
                    </p>
                    {selectedRun.degraded_reason && (
                      <p className="mt-1.5 font-mono text-xs bg-white/70 p-2 rounded border border-amber-100">
                        {selectedRun.degraded_reason}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Interrupted Banner (DESIGN 4.8) */}
            {selectedRun.status === 'INTERRUPTED' && (
              <div
                role="region"
                aria-label="Run Interrupted"
                className="mt-5 p-4 bg-orange-50 border border-orange-200 rounded-lg text-sm text-[#C2410C]"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-2.5">
                    <ShieldAlert className="w-5 h-5 text-[#EA580C] shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold">This run stopped before it finished</p>
                      <p className="text-xs mt-0.5">
                        Execution was interrupted. You can resume safely from the last saved SQLite checkpoint without repeating completed tasks.
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    isLoading={isResuming}
                    leftIcon={<Play className="w-3.5 h-3.5" />}
                    onClick={handleResumeRun}
                  >
                    Resume
                  </Button>
                </div>
              </div>
            )}

            {/* Budget Stop Banner */}
            {selectedRun.stop_reason === 'step_budget_exceeded' && (
              <div className="mt-5 p-4 bg-slate-100 border border-slate-200 rounded-lg text-sm text-[#475569]">
                <div className="flex items-center gap-2 font-medium text-[#1E293B]">
                  <Layers className="w-4 h-4 text-[#6366F1]" />
                  <span>Execution step budget reached ({selectedRun.depth_level})</span>
                </div>
                <p className="text-xs text-[#64748B] mt-1">
                  Run reached its step limit. Check the routing log timeline below for unfinished tasks.
                </p>
              </div>
            )}
          </Card>

          {/* Detail Tabs */}
          <div className="flex border-b border-[#E2E8F0]">
            <button
              onClick={() => setActiveTab('timeline')}
              className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors cursor-pointer flex items-center gap-2 ${
                activeTab === 'timeline'
                  ? 'border-[#6366F1] text-[#6366F1]'
                  : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
              }`}
            >
              <History className="w-4 h-4" />
              Routing Log Timeline ({routingLogs.length})
            </button>
            <button
              onClick={() => setActiveTab('tasks')}
              className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors cursor-pointer flex items-center gap-2 ${
                activeTab === 'tasks'
                  ? 'border-[#6366F1] text-[#6366F1]'
                  : 'border-transparent text-[#64748B] hover:text-[#0F172A]'
              }`}
            >
              <ListOrdered className="w-4 h-4" />
              Execution Tasks ({selectedRun.tasks ? selectedRun.tasks.length : 0})
            </button>
          </div>

          {/* TAB 1: ROUTING TIMELINE */}
          {activeTab === 'timeline' && (
            <Card className="p-6">
              {isLoadingDetail ? (
                <div className="py-12 text-center text-[#64748B] text-sm flex flex-col items-center justify-center">
                  <RefreshCw className="w-6 h-6 animate-spin text-[#6366F1] mb-2" />
                  Loading routing log timeline...
                </div>
              ) : routingLogs.length === 0 ? (
                <div className="py-12 text-center text-[#64748B] text-sm">
                  No routing steps recorded for this run yet.
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-200">
                    {routingLogs.map((log: RoutingLogItem) => (
                      <div key={log.step_number} className="relative group">
                        {/* Circle bullet on timeline */}
                        <div
                          className={`absolute -left-6 top-1.5 w-5 h-5 rounded-full border-2 bg-white flex items-center justify-center ${
                            log.output_status === 'fallback'
                              ? 'border-amber-500 text-amber-600'
                              : 'border-indigo-500 text-indigo-600'
                          }`}
                        >
                          <span className="text-[10px] font-bold">{log.step_number}</span>
                        </div>

                        {/* Step Card Content */}
                        <div className="bg-slate-50/80 hover:bg-slate-50 transition-colors border border-slate-200 rounded-lg p-4">
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200/60 pb-3">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-sm text-[#0F172A] capitalize">
                                {log.from_node}
                              </span>
                              <ArrowRight className="w-3.5 h-3.5 text-[#94A3B8]" />
                              <span className="font-semibold text-sm text-[#6366F1] capitalize">
                                {log.to_node}
                              </span>
                              <span className="text-xs text-[#94A3B8]">
                                (Step {log.step_number})
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              {/* Decided by badge (DESIGN 4.8) */}
                              <Badge
                                variant={log.decided_by === 'model' ? 'primary' : 'neutral'}
                                size="sm"
                                className="flex items-center gap-1 font-mono text-[11px]"
                              >
                                {log.decided_by === 'model' ? (
                                  <>
                                    <Bot className="w-3 h-3" />
                                    Model
                                  </>
                                ) : (
                                  <>
                                    <Code2 className="w-3 h-3" />
                                    Code
                                  </>
                                )}
                              </Badge>

                              {log.output_status === 'fallback' && (
                                <Badge variant="warning" size="sm">
                                  Fallback
                                </Badge>
                              )}

                              <span className="text-xs text-[#64748B] flex items-center gap-1">
                                <Coins className="w-3 h-3 text-[#D97706]" />
                                {log.tokens_in + log.tokens_out} tokens
                              </span>
                            </div>
                          </div>

                          {/* Reason */}
                          <div className="mt-3">
                            <p className="text-xs text-[#64748B] font-medium mb-1">Routing Reason:</p>
                            <p className="text-sm text-[#1E293B] bg-white p-2.5 rounded border border-slate-200/80">
                              {log.reason}
                            </p>
                          </div>

                          {/* Eligible Nodes & Badges */}
                          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                            <div className="flex items-center gap-1.5">
                              <span className="text-[#64748B]">Eligible nodes:</span>
                              <div className="flex flex-wrap gap-1">
                                {log.eligible_nodes.map((node) => (
                                  <span
                                    key={node}
                                    className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${
                                      node === log.to_node
                                        ? 'bg-indigo-100 text-indigo-800 font-semibold'
                                        : 'bg-slate-200/80 text-slate-700'
                                    }`}
                                  >
                                    {node}
                                  </span>
                                ))}
                              </div>
                            </div>

                            {log.invalid_category && (
                              <Badge variant="error" size="sm">
                                Invalid Output: {log.invalid_category}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* TAB 2: TASKS */}
          {activeTab === 'tasks' && (
            <Card className="p-6">
              {!selectedRun.tasks || selectedRun.tasks.length === 0 ? (
                <div className="py-12 text-center text-[#64748B] text-sm">
                  No execution tasks decomposed for this run yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {selectedRun.tasks.map((task: TaskResponse) => (
                    <div
                      key={task.id}
                      className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between gap-4"
                    >
                      <div className="flex items-center gap-3">
                        <span className="w-6 h-6 rounded-full bg-white border border-slate-300 text-xs font-bold text-[#64748B] flex items-center justify-center shrink-0">
                          {task.position}
                        </span>
                        <div>
                          <p className="text-sm font-medium text-[#0F172A]">{task.title}</p>
                          <p className="text-xs text-[#64748B] capitalize mt-0.5">
                            Agent: <span className="font-mono text-slate-700">{task.agent}</span>
                          </p>
                        </div>
                      </div>
                      <Badge variant={TASK_STATUS_VARIANTS[task.status] || 'neutral'}>
                        {task.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>
      ) : (
        /* RUNS LIST VIEW */
        <div className="space-y-4">
          {/* Filters Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-[#E2E8F0]">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-[#64748B] mr-1">Status:</span>
              {['ALL', 'RUNNING', 'WAITING_APPROVAL', 'COMPLETED', 'INTERRUPTED', 'STOPPED', 'FAILED'].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`px-2.5 py-1 text-xs rounded-full border transition-colors cursor-pointer ${
                    statusFilter === st
                      ? 'bg-[#6366F1] text-white border-[#6366F1]'
                      : 'bg-white text-[#64748B] border-slate-200 hover:border-slate-300'
                  }`}
                >
                  {st === 'ALL' ? 'All' : st.replace(/_/g, ' ')}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[#64748B]">Type:</span>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-[#0F172A] focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="ALL">All Types</option>
                <option value="goal">Goal Strategy</option>
                <option value="weekly_brief">Weekly Brief</option>
                <option value="post_mortem">Post-Mortem</option>
              </select>
            </div>
          </div>

          {/* Runs List Items */}
          {isLoadingRuns ? (
            <div className="py-16 text-center text-[#64748B] text-sm flex flex-col items-center justify-center">
              <RefreshCw className="w-8 h-8 animate-spin text-[#6366F1] mb-2" />
              Loading runs history...
            </div>
          ) : runs.length === 0 ? (
            <Card className="py-16 text-center text-[#64748B] text-sm">
              <History className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <p className="font-medium text-[#0F172A]">No execution runs found</p>
              <p className="text-xs text-[#64748B] mt-1">
                {statusFilter !== 'ALL' || typeFilter !== 'ALL'
                  ? 'No runs match the selected filters.'
                  : 'Start a goal run on the Home tab to see execution progress here.'}
              </p>
            </Card>
          ) : (
            <div className="space-y-3">
              {runs.map((run: RunResponse) => (
                <Card
                  key={run.id}
                  className="p-5 hover:border-indigo-200 hover:shadow-sm transition-all cursor-pointer"
                  onClick={() => setSelectedRunId(run.id)}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-sm text-[#0F172A] font-mono">
                          {run.id.slice(0, 8)}...
                        </span>
                        <Badge variant={STATUS_VARIANTS[run.status]}>
                          {run.status}
                        </Badge>
                        <Badge variant="primary" className="uppercase text-[10px]">
                          {run.depth_level}
                        </Badge>
                        <Badge variant="neutral" className="capitalize text-[10px]">
                          {run.run_type.replace(/_/g, ' ')}
                        </Badge>
                        {run.degraded && (
                          <Badge variant="warning" className="flex items-center gap-1 text-[10px]">
                            <AlertTriangle className="w-3 h-3" />
                            Degraded
                          </Badge>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-4 text-xs text-[#64748B]">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5" />
                          {new Date(run.created_at).toLocaleDateString([], {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                        <span className="flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          {run.step_count} steps
                        </span>
                        <span className="flex items-center gap-1">
                          <Coins className="w-3.5 h-3.5 text-[#D97706]" />
                          {run.tokens_used.toLocaleString()} tokens
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-center text-sm font-medium text-[#6366F1]">
                      <span>View Details</span>
                      <ChevronRight className="w-4 h-4" />
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Cancel Active Run Modal */}
      <Modal
        isOpen={isCancelModalOpen}
        onClose={() => setIsCancelModalOpen(false)}
        title="Cancel Execution Run?"
      >
        <div className="space-y-4">
          <p className="text-sm text-[#64748B]">
            Are you sure you want to stop this run? Execution will halt cooperatively at the next step boundary, and any unfinished tasks will be cancelled.
          </p>
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-[#E2E8F0]">
            <Button
              variant="outline"
              size="sm"
              disabled={isCancelling}
              onClick={() => setIsCancelModalOpen(false)}
            >
              Keep Running
            </Button>
            <Button
              variant="destructive"
              size="sm"
              isLoading={isCancelling}
              onClick={handleCancelRun}
            >
              Yes, Cancel Run
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
