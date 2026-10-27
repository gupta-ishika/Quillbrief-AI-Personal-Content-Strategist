import React, { useState, useEffect, useRef } from 'react';
import {
  Zap,
  Compass,
  Layers,
  ArrowRight,
  StopCircle,
  Play,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Coins,
  Bot,
  ExternalLink,
} from 'lucide-react';
import { apiClient, ApiClientError } from '../../api/client';
import { DepthLevel, RunResponse, TaskResponse } from '../../types';
import { Button } from '../common/Button';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { Modal } from '../common/Modal';

export interface HomeScreenProps {
  onNavigateToApprovals: (approvalId?: string) => void;
}

const DEPTH_OPTIONS: Array<{
  id: DepthLevel;
  title: string;
  badge: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  {
    id: 'quick',
    title: 'Quick',
    badge: '1-2 mins',
    description: 'Minimal search & synthesis for quick concept outlines.',
    icon: Zap,
  },
  {
    id: 'standard',
    title: 'Standard',
    badge: 'Recommended',
    description: 'Balanced research, audience comments and structured plan.',
    icon: Compass,
  },
  {
    id: 'deep',
    title: 'Deep',
    badge: 'Exhaustive',
    description: 'Exhaustive exploration, competitive context & deep analysis.',
    icon: Layers,
  },
];

export const HomeScreen: React.FC<HomeScreenProps> = ({
  onNavigateToApprovals,
}) => {
  const [goalText, setGoalText] = useState<string>('');
  const [depthLevel, setDepthLevel] = useState<DepthLevel>('standard');
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [startError, setStartError] = useState<string | null>(null);

  // Active or latest tracked run
  const [activeRun, setActiveRun] = useState<RunResponse | null>(null);
  const [cancelModalOpen, setCancelModalOpen] = useState<boolean>(false);
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [isResuming, setIsResuming] = useState<boolean>(false);

  const pollIntervalRef = useRef<number | null>(null);
  const pollCountRef = useRef<number>(0);

  // Load existing active or recent runs
  const fetchRecentRuns = async () => {
    try {
      const runs = await apiClient.listRuns();
      if (runs && runs.length > 0) {
        // Find if there is an active run (RUNNING, WAITING_APPROVAL, PENDING, INTERRUPTED)
        const inProgress = runs.find((r) =>
          ['RUNNING', 'WAITING_APPROVAL', 'PENDING', 'INTERRUPTED'].includes(r.status)
        );
        if (inProgress) {
          setActiveRun(inProgress);
        } else if (!activeRun) {
          // If no active run, optionally show the latest completed/failed run
          setActiveRun(runs[0]);
        }
      }
    } catch {
      // Ignore initial list error
    }
  };

  useEffect(() => {
    fetchRecentRuns();
  }, []);

  // Polling for active run
  useEffect(() => {
    if (!activeRun) return;

    const isRunning = ['RUNNING', 'PENDING'].includes(activeRun.status);

    if (isRunning) {
      pollCountRef.current = 0;

      const schedulePoll = () => {
        // Every 2s for first minute (30 polls), then every 5s
        const intervalMs = pollCountRef.current < 30 ? 2000 : 5000;
        pollIntervalRef.current = window.setTimeout(async () => {
          try {
            pollCountRef.current += 1;
            const updated = await apiClient.getRun(activeRun.id);
            setActiveRun(updated);
            if (['RUNNING', 'PENDING'].includes(updated.status)) {
              schedulePoll();
            }
          } catch {
            // Retry next tick
            schedulePoll();
          }
        }, intervalMs);
      };

      schedulePoll();

      return () => {
        if (pollIntervalRef.current) {
          clearTimeout(pollIntervalRef.current);
        }
      };
    }
  }, [activeRun?.id, activeRun?.status]);

  // Start new run
  const handleStartRun = async () => {
    const trimmed = goalText.trim();
    if (!trimmed) return;

    setIsStarting(true);
    setStartError(null);
    try {
      const res = await apiClient.createRun({
        goal_text: trimmed,
        depth_level: depthLevel,
      });

      // Fetch the created run details
      const newRun = await apiClient.getRun(res.run_id);
      setActiveRun(newRun);
      setGoalText('');
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.code === 'RUN_ACTIVE') {
        setStartError('Another run is currently active. Please wait or cancel the active run first.');
      } else if (err instanceof ApiClientError && err.code === 'ONBOARDING_REQUIRED') {
        setStartError('Please complete first-run onboarding before launching strategy runs.');
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to start run. Please retry.';
        setStartError(msg);
      }
    } finally {
      setIsStarting(false);
    }
  };

  // Cancel run
  const handleConfirmCancel = async () => {
    if (!activeRun) return;
    setIsCancelling(true);
    try {
      await apiClient.cancelRun(activeRun.id);
      const updated = await apiClient.getRun(activeRun.id);
      setActiveRun(updated);
      setCancelModalOpen(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to cancel run.';
      setStartError(msg);
    } finally {
      setIsCancelling(false);
    }
  };

  // Resume interrupted run
  const handleResumeRun = async () => {
    if (!activeRun) return;
    setIsResuming(true);
    try {
      await apiClient.resumeRun(activeRun.id);
      const updated = await apiClient.getRun(activeRun.id);
      setActiveRun(updated);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to resume run.';
      setStartError(msg);
    } finally {
      setIsResuming(false);
    }
  };

  const isCurrentRunActive = Boolean(
    activeRun && ['RUNNING', 'PENDING'].includes(activeRun.status)
  );

  return (
    <div className="space-y-8">
      {/* Page Title */}
      <div>
        <h1 className="text-2xl font-semibold text-[#0F172A] tracking-tight">
          Create Strategy
        </h1>
        <p className="text-sm text-[#64748B] mt-1">
          Specify your content goal. The local multi-agent system will analyze comments, identify topics, and synthesize a proposed plan.
        </p>
      </div>

      {/* Goal creation card */}
      <Card className="p-6 space-y-6">
        <div>
          <label
            htmlFor="goal-input"
            className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-2"
          >
            What is your content goal? *
          </label>
          <textarea
            id="goal-input"
            rows={3}
            value={goalText}
            onChange={(e) => setGoalText(e.target.value)}
            disabled={isCurrentRunActive || isStarting}
            placeholder="e.g., Plan 3 technical tutorials on building FastAPI agents with local LLMs and LangGraph, focusing on practical deployment patterns."
            className="w-full px-4 py-3 bg-white border border-[#E2E8F0] rounded-xl text-sm text-[#0F172A] placeholder-[#64748B]/60 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all disabled:bg-slate-50 disabled:opacity-75"
          />
        </div>

        {/* Depth Level Selector */}
        <div>
          <label className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider mb-2.5">
            Research Depth Level
          </label>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {DEPTH_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const isSelected = depthLevel === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setDepthLevel(opt.id)}
                  disabled={isCurrentRunActive || isStarting}
                  className={`p-4 rounded-xl border text-left transition-all cursor-pointer select-none ${
                    isSelected
                      ? 'border-[#6366F1] bg-indigo-50/50 shadow-xs ring-1 ring-[#6366F1]'
                      : 'border-[#E2E8F0] bg-white hover:bg-slate-50'
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Icon
                        className={`w-4 h-4 ${
                          isSelected ? 'text-[#6366F1]' : 'text-[#64748B]'
                        }`}
                      />
                      <span className="text-sm font-semibold text-[#0F172A]">
                        {opt.title}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                        isSelected
                          ? 'bg-indigo-100 text-[#6366F1]'
                          : 'bg-slate-100 text-[#64748B]'
                      }`}
                    >
                      {opt.badge}
                    </span>
                  </div>
                  <p className="text-xs text-[#64748B] leading-relaxed">
                    {opt.description}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Error notice */}
        {startError && (
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-[#DC2626]">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="flex-1 font-medium">{startError}</div>
          </div>
        )}

        {/* Action Button */}
        <div className="flex items-center justify-between pt-2">
          <span className="text-xs text-[#64748B]">
            All synthesis runs locally through Ollama. Zero data leaves your machine.
          </span>
          <Button
            onClick={handleStartRun}
            disabled={!goalText.trim() || isCurrentRunActive}
            isLoading={isStarting}
            rightIcon={<ArrowRight className="w-4 h-4" />}
          >
            Start Strategy Run
          </Button>
        </div>
      </Card>

      {/* Active or Tracked Run Card */}
      {activeRun && (
        <Card className="p-6 space-y-5 border-indigo-100 shadow-md">
          {/* Header */}
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
            <div>
              <div className="flex items-center gap-2.5 mb-1">
                <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wider">
                  Active Run
                </span>
                <Badge
                  variant={
                    activeRun.status === 'RUNNING'
                      ? 'primary'
                      : activeRun.status === 'WAITING_APPROVAL'
                      ? 'warning'
                      : activeRun.status === 'COMPLETED'
                      ? 'success'
                      : activeRun.status === 'INTERRUPTED'
                      ? 'warning'
                      : 'neutral'
                  }
                >
                  {activeRun.status}
                </Badge>
                <Badge variant="neutral" size="sm">
                  {activeRun.depth_level}
                </Badge>
              </div>
              <h2 className="text-base font-semibold text-[#0F172A]">
                {activeRun.run_type === 'weekly_brief'
                  ? 'Weekly Brief Synthesis'
                  : 'Goal Strategy Decomposition'}
              </h2>
            </div>

            {/* Run Actions */}
            <div className="flex items-center gap-2">
              {activeRun.status === 'WAITING_APPROVAL' && (
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => onNavigateToApprovals(activeRun.pending_approval_id || undefined)}
                  rightIcon={<ExternalLink className="w-3.5 h-3.5" />}
                >
                  Review Approval
                </Button>
              )}

              {activeRun.status === 'INTERRUPTED' && (
                <Button
                  size="sm"
                  variant="primary"
                  onClick={handleResumeRun}
                  isLoading={isResuming}
                  leftIcon={<Play className="w-3.5 h-3.5" />}
                >
                  Resume Run
                </Button>
              )}

              {['RUNNING', 'PENDING', 'WAITING_APPROVAL', 'INTERRUPTED'].includes(
                activeRun.status
              ) && (
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => setCancelModalOpen(true)}
                  leftIcon={<StopCircle className="w-3.5 h-3.5" />}
                >
                  Cancel
                </Button>
              )}
            </div>
          </div>

          {/* Degraded Run Warning Banner */}
          {activeRun.degraded && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-[#D97706] flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-0.5">Degraded Run Notice</p>
                <p className="leading-relaxed">
                  Some steps used default choices or missing tools, so this result may be incomplete.
                  {activeRun.degraded_reason && (
                    <span className="block mt-1 font-mono text-[11px] bg-amber-100/60 p-1.5 rounded">
                      Reason: {activeRun.degraded_reason}
                    </span>
                  )}
                </p>
              </div>
            </div>
          )}

          {/* Interrupted notice */}
          {activeRun.status === 'INTERRUPTED' && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-[#D97706] flex items-start gap-3">
              <Clock className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-0.5">Run Interrupted</p>
                <p className="leading-relaxed">
                  This run stopped before it finished (e.g. process restart). You can resume execution from the last recorded checkpoint.
                </p>
              </div>
            </div>
          )}

          {/* Live Progress Indicators */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-slate-50 rounded-xl border border-[#E2E8F0] text-xs">
            <div>
              <span className="text-[#64748B] block mb-1">Current Agent</span>
              <span className="font-semibold text-[#0F172A] flex items-center gap-1.5 capitalize">
                <Bot className="w-3.5 h-3.5 text-[#6366F1]" />
                {activeRun.current_node ? activeRun.current_node.replace(/_/g, ' ') : 'Idle'}
              </span>
            </div>
            <div>
              <span className="text-[#64748B] block mb-1">Step Count</span>
              <span className="font-semibold text-[#0F172A]">
                {activeRun.step_count} steps
              </span>
            </div>
            <div>
              <span className="text-[#64748B] block mb-1">Tokens Used</span>
              <span className="font-semibold text-[#0F172A] flex items-center gap-1">
                <Coins className="w-3.5 h-3.5 text-amber-500" />
                {activeRun.tokens_used.toLocaleString()}
              </span>
            </div>
            <div>
              <span className="text-[#64748B] block mb-1">Status</span>
              <span className="font-semibold text-[#0F172A]">
                {activeRun.status}
              </span>
            </div>
          </div>

          {/* Task decomposition list */}
          {activeRun.tasks && activeRun.tasks.length > 0 && (
            <div className="space-y-2.5">
              <span className="text-xs font-semibold text-[#0F172A] uppercase tracking-wider block">
                Execution Task List ({activeRun.tasks.filter((t) => t.status === 'DONE').length}/{activeRun.tasks.length})
              </span>
              <div className="space-y-1.5">
                {activeRun.tasks.map((task: TaskResponse) => (
                  <div
                    key={task.id}
                    className="p-3 bg-white border border-[#E2E8F0] rounded-lg flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2.5">
                      {task.status === 'DONE' ? (
                        <CheckCircle2 className="w-4 h-4 text-[#16A34A] shrink-0" />
                      ) : task.status === 'FAILED' ? (
                        <AlertTriangle className="w-4 h-4 text-[#DC2626] shrink-0" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border-2 border-slate-300 border-t-indigo-500 animate-spin shrink-0" />
                      )}
                      <span className="font-medium text-[#0F172A]">
                        {task.title}
                      </span>
                    </div>
                    <Badge variant="neutral" size="sm">
                      {task.agent}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Confirmation Modal for Cancel */}
      <Modal
        isOpen={cancelModalOpen}
        onClose={() => setCancelModalOpen(false)}
        title="Cancel Active Run?"
        description="Are you sure you want to cancel this strategy run?"
      >
        <div className="space-y-4 text-sm text-[#64748B]">
          <p>
            The run will stop at the next step boundary. Any tools currently in progress will terminate, and unreviewed approvals will be cancelled.
          </p>
          <div className="flex justify-end gap-2.5 pt-2">
            <Button
              variant="outline"
              onClick={() => setCancelModalOpen(false)}
              disabled={isCancelling}
            >
              Keep Running
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmCancel}
              isLoading={isCancelling}
            >
              Yes, Cancel Run
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
