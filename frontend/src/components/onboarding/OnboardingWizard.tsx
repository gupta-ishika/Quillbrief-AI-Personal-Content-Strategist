import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Video,
  Loader2,
} from 'lucide-react';
import { apiClient, ApiClientError } from '../../api/client';
import {
  OnboardingStep,
  SettingsResponse,
  TonePreset,
} from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';

export interface OnboardingWizardProps {
  onCompleted: () => void;
}

const TONE_PRESETS: Array<{
  id: TonePreset;
  title: string;
  description: string;
}> = [
  {
    id: 'professional',
    title: 'Professional',
    description: 'Clear, structured, authoritative and industry-standard.',
  },
  {
    id: 'friendly',
    title: 'Friendly',
    description: 'Approachable, warm, engaging and community-focused.',
  },
  {
    id: 'educational',
    title: 'Educational',
    description: 'Step-by-step explanatory, insightful and instructive.',
  },
  {
    id: 'conversational',
    title: 'Conversational',
    description: 'Casual, relatable, direct and candid.',
  },
  {
    id: 'humorous',
    title: 'Humorous',
    description: 'Witty, entertaining, clever and light-hearted.',
  },
];

export const OnboardingWizard: React.FC<OnboardingWizardProps> = ({
  onCompleted,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  // Current step: 1 (niche), 2 (tone), 3 (channel), 4 (review)
  const [stepNumber, setStepNumber] = useState<number>(1);

  // Form values
  const [niche, setNiche] = useState<string>('');
  const [tonePreset, setTonePreset] = useState<TonePreset | ''>('');
  const [toneInstructions, setToneInstructions] = useState<string>('');
  const [channelInput, setChannelInput] = useState<string>('');

  // Resolved channel state
  const [resolvedChannel, setResolvedChannel] = useState<{
    channel_id?: string | null;
    handle?: string | null;
    title?: string | null;
    verified: boolean;
  } | null>(null);
  const [resolvingChannel, setResolvingChannel] = useState<boolean>(false);
  const [resolveFeedback, setResolveFeedback] = useState<{
    type: 'success' | 'error' | 'warning';
    message: string;
  } | null>(null);

  // Server state metadata
  const [apiKeyConfigured, setApiKeyConfigured] = useState<boolean>(false);
  const [youtubeOAuthState, setYoutubeOAuthState] = useState<'connected' | 'needs_reauth' | 'disconnected'>('disconnected');
  const [settings, setSettings] = useState<SettingsResponse | null>(null);

  // Load initial onboarding state
  const loadState = async () => {
    setLoading(true);
    setGeneralError(null);
    try {
      const [onbData, settingsData] = await Promise.all([
        apiClient.getOnboarding(),
        apiClient.getSettings(),
      ]);

      setSettings(settingsData);
      setApiKeyConfigured(onbData.values.api_key_configured);
      setYoutubeOAuthState(onbData.values.youtube_oauth.state);

      if (onbData.values.niche) {
        setNiche(onbData.values.niche);
      }
      if (onbData.values.tone_preset) {
        setTonePreset(onbData.values.tone_preset as TonePreset);
      }
      if (onbData.values.tone_instructions) {
        setToneInstructions(onbData.values.tone_instructions);
      }
      if (onbData.values.channel) {
        setResolvedChannel(onbData.values.channel);
        setChannelInput(onbData.values.channel.handle || onbData.values.channel.channel_id || '');
      }

      if (onbData.onboarding_completed) {
        onCompleted();
        return;
      }

      // Map next_step to stepNumber
      const stepMap: Record<OnboardingStep, number> = {
        niche: 1,
        tone: 2,
        channel: 3,
        review: 4,
      };
      setStepNumber(stepMap[onbData.next_step] || 1);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load onboarding status.';
      setGeneralError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadState();
  }, []);

  // Step 1: Save Niche
  const handleContinueNiche = async () => {
    const trimmed = niche.trim();
    if (!trimmed || trimmed.length > 200) return;

    setSubmitting(true);
    setGeneralError(null);
    try {
      await apiClient.updateSettings({ niche: trimmed });
      setNiche(trimmed);
      setStepNumber(2);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save niche.';
      setGeneralError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // Step 2: Save Tone
  const handleContinueTone = async () => {
    if (!tonePreset) return;
    const trimmedInstructions = toneInstructions.trim();
    if (trimmedInstructions.length > 500) return;

    setSubmitting(true);
    setGeneralError(null);
    try {
      await apiClient.updateSettings({
        tone_preset: tonePreset as TonePreset,
        tone_instructions: trimmedInstructions,
      });
      setToneInstructions(trimmedInstructions);
      setStepNumber(3);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save tone preferences.';
      setGeneralError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // Step 3: Check / Resolve Channel
  const handleCheckChannel = async () => {
    const idToTest = channelInput.trim();
    if (!idToTest) return;

    setResolvingChannel(true);
    setResolveFeedback(null);
    try {
      const res = await apiClient.resolveChannel(idToTest);
      if (res.resolved) {
        setResolvedChannel({
          channel_id: res.channel_id || null,
          title: res.title || null,
          handle: idToTest.startsWith('@') ? idToTest : null,
          verified: true,
        });
        setResolveFeedback({
          type: 'success',
          message: `Found channel: "${res.title}"`,
        });
      } else if (res.reason === 'API_KEY_NOT_CONFIGURED') {
        setResolvedChannel({
          channel_id: res.parsed?.type === 'channel_id' ? res.parsed.value : null,
          handle: res.parsed?.type === 'handle' ? res.parsed.value : null,
          title: null,
          verified: false,
        });
        setResolveFeedback({
          type: 'warning',
          message: `Format valid (${res.parsed?.type}). Will be saved as unverified since API key is not configured.`,
        });
      } else {
        setResolveFeedback({
          type: 'error',
          message: 'Channel not found or lookup failed.',
        });
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.code === 'CHANNEL_IDENTIFIER_INVALID') {
        setResolveFeedback({
          type: 'error',
          message: 'Paste your @handle or channel ID instead.',
        });
      } else if (err instanceof ApiClientError && err.status === 404) {
        setResolveFeedback({
          type: 'error',
          message: 'Channel not found.',
        });
      } else {
        const msg = err instanceof Error ? err.message : 'Lookup failed.';
        setResolveFeedback({
          type: 'error',
          message: msg,
        });
      }
    } finally {
      setResolvingChannel(false);
    }
  };

  // Step 3: Save Channel & Continue
  const handleContinueChannel = async () => {
    const trimmed = channelInput.trim();
    if (!trimmed) {
      handleSkipChannel();
      return;
    }

    setSubmitting(true);
    setGeneralError(null);
    try {
      const res = await apiClient.updateCreatorChannel({ identifier: trimmed });
      setResolvedChannel(res);
      // Refresh settings for review step
      const freshSettings = await apiClient.getSettings();
      setSettings(freshSettings);
      setStepNumber(4);
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.code === 'CHANNEL_IDENTIFIER_INVALID') {
        setResolveFeedback({
          type: 'error',
          message: 'Paste your @handle or channel ID instead.',
        });
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to save channel.';
        setGeneralError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Step 3: Skip Channel
  const handleSkipChannel = async () => {
    setSubmitting(true);
    setGeneralError(null);
    try {
      await apiClient.skipOnboardingChannel();
      const freshSettings = await apiClient.getSettings();
      setSettings(freshSettings);
      setStepNumber(4);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to skip channel step.';
      setGeneralError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // Step 3: YouTube OAuth Start
  const handleConnectOAuth = async () => {
    setSubmitting(true);
    setGeneralError(null);
    try {
      const res = await apiClient.startYouTubeOAuth('onboarding');
      window.location.href = res.authorization_url;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to initiate YouTube connection.';
      setGeneralError(msg);
      setSubmitting(false);
    }
  };

  // Step 4: Finish setup
  const handleFinishSetup = async () => {
    setSubmitting(true);
    setGeneralError(null);
    try {
      const res = await apiClient.completeOnboarding();
      if (res.onboarding_completed) {
        onCompleted();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to finish setup. Please retry.';
      setGeneralError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex flex-col items-center justify-center p-6">
        <Loader2 className="w-8 h-8 animate-spin text-[#6366F1] mb-3" />
        <p className="text-sm text-[#64748B]">Loading setup preferences...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col justify-center items-center p-4 sm:p-6 lg:p-8">
      {/* Container card */}
      <div className="max-w-xl w-full bg-white rounded-2xl shadow-sm border border-[#E2E8F0] overflow-hidden">
        {/* Card Header with Progress */}
        <div className="px-6 sm:px-8 pt-8 pb-5 border-b border-[#E2E8F0] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-[#6366F1]">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-[#0F172A]">
                Welcome to Quillbrief AI
              </h2>
              <p className="text-xs text-[#64748B]">First-run setup</p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-indigo-50 text-[#6366F1]">
            Step {stepNumber} of 4
          </span>
        </div>

        {/* Global Error Banner */}
        {generalError && (
          <div className="mx-6 sm:mx-8 mt-6 p-3 rounded-lg bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-[#DC2626]">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="flex-1">
              <span className="font-medium">{generalError}</span>
            </div>
            <button
              onClick={() => setGeneralError(null)}
              className="text-[#DC2626] font-semibold hover:underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Step 1: Niche */}
        {stepNumber === 1 && (
          <div className="p-6 sm:p-8 space-y-6">
            <div>
              <h1 className="text-xl font-semibold text-[#0F172A] tracking-tight">
                Your niche
              </h1>
              <p className="text-sm text-[#64748B] mt-1">
                What do you create content about?
              </p>
            </div>

            <div className="space-y-2">
              <label
                htmlFor="niche-input"
                className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider"
              >
                Niche & Focus Areas *
              </label>
              <input
                id="niche-input"
                type="text"
                value={niche}
                onChange={(e) => setNiche(e.target.value)}
                placeholder="e.g., Python tutorials, backend development and FastAPI"
                maxLength={200}
                className="w-full px-3.5 py-2.5 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] placeholder-[#64748B]/60 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
              />
              <div className="flex justify-between items-center text-xs">
                <span className="text-[#64748B]">
                  Be specific so suggested topics align with your domain.
                </span>
                <span
                  className={`font-mono font-medium ${
                    niche.length > 200 ? 'text-[#DC2626]' : 'text-[#64748B]'
                  }`}
                >
                  {niche.length}/200
                </span>
              </div>
            </div>

            <div className="pt-4 flex justify-end">
              <Button
                onClick={handleContinueNiche}
                disabled={!niche.trim() || niche.length > 200}
                isLoading={submitting}
                rightIcon={<ArrowRight className="w-4 h-4" />}
              >
                Continue
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Tone */}
        {stepNumber === 2 && (
          <div className="p-6 sm:p-8 space-y-6">
            <div>
              <h1 className="text-xl font-semibold text-[#0F172A] tracking-tight">
                Your tone
              </h1>
              <p className="text-sm text-[#64748B] mt-1">
                How should your content sound?
              </p>
            </div>

            <div className="space-y-3">
              <label className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider">
                Select Tone Preset *
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {TONE_PRESETS.map((preset) => {
                  const isSelected = tonePreset === preset.id;
                  return (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => setTonePreset(preset.id)}
                      className={`text-left p-3.5 rounded-xl border transition-all cursor-pointer select-none ${
                        isSelected
                          ? 'border-[#6366F1] bg-indigo-50/50 shadow-xs ring-1 ring-[#6366F1]'
                          : 'border-[#E2E8F0] bg-white hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-semibold text-[#0F172A]">
                          {preset.title}
                        </span>
                        {isSelected && (
                          <CheckCircle2 className="w-4 h-4 text-[#6366F1]" />
                        )}
                      </div>
                      <p className="text-xs text-[#64748B] leading-relaxed">
                        {preset.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-2 pt-2">
              <label
                htmlFor="tone-instructions"
                className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider"
              >
                Additional Tone Instructions (optional)
              </label>
              <textarea
                id="tone-instructions"
                rows={3}
                value={toneInstructions}
                onChange={(e) => setToneInstructions(e.target.value)}
                placeholder="e.g., Avoid buzzwords, use concrete code examples, maintain a direct and humble style."
                maxLength={500}
                className="w-full px-3.5 py-2.5 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] placeholder-[#64748B]/60 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
              />
              <div className="flex justify-between items-center text-xs">
                <span className="text-[#64748B]">
                  Specific phrases or guidelines you prefer the agents to follow.
                </span>
                <span
                  className={`font-mono font-medium ${
                    toneInstructions.length > 500
                      ? 'text-[#DC2626]'
                      : 'text-[#64748B]'
                  }`}
                >
                  {toneInstructions.length}/500
                </span>
              </div>
            </div>

            <div className="pt-4 flex items-center justify-between">
              <Button
                variant="outline"
                onClick={() => setStepNumber(1)}
                leftIcon={<ArrowLeft className="w-4 h-4" />}
              >
                Back
              </Button>
              <Button
                onClick={handleContinueTone}
                disabled={!tonePreset || toneInstructions.length > 500}
                isLoading={submitting}
                rightIcon={<ArrowRight className="w-4 h-4" />}
              >
                Continue
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Channel */}
        {stepNumber === 3 && (
          <div className="p-6 sm:p-8 space-y-6">
            <div>
              <h1 className="text-xl font-semibold text-[#0F172A] tracking-tight">
                Your YouTube channel
              </h1>
              <p className="text-sm text-[#64748B] mt-1">
                Connect your channel for performance context and audience insights. (Optional)
              </p>
            </div>

            {!apiKeyConfigured && (
              <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-3 text-xs text-[#D97706]">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <p className="leading-relaxed">
                  Public video and comment data is unavailable until <code className="font-mono bg-amber-100 px-1 py-0.5 rounded">YOUTUBE_API_KEY</code> is set in your <code className="font-mono bg-amber-100 px-1 py-0.5 rounded">.env</code> file and the backend is restarted. A handle you enter now is saved as unverified.
                </p>
              </div>
            )}

            <div className="space-y-3">
              <label
                htmlFor="channel-input"
                className="block text-xs font-semibold text-[#0F172A] uppercase tracking-wider"
              >
                Channel handle, ID or URL
              </label>
              <div className="flex gap-2">
                <input
                  id="channel-input"
                  type="text"
                  value={channelInput}
                  onChange={(e) => {
                    setChannelInput(e.target.value);
                    setResolveFeedback(null);
                  }}
                  placeholder="@yourhandle or UCxxxxxxxxxxxxxxxx"
                  className="flex-1 px-3.5 py-2.5 bg-white border border-[#E2E8F0] rounded-lg text-sm text-[#0F172A] placeholder-[#64748B]/60 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
                />
                <Button
                  variant="outline"
                  onClick={handleCheckChannel}
                  disabled={!channelInput.trim()}
                  isLoading={resolvingChannel}
                >
                  Check
                </Button>
              </div>

              {resolveFeedback && (
                <div
                  className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                    resolveFeedback.type === 'success'
                      ? 'bg-green-50 text-[#16A34A] border border-green-200'
                      : resolveFeedback.type === 'warning'
                      ? 'bg-amber-50 text-[#D97706] border border-amber-200'
                      : 'bg-red-50 text-[#DC2626] border border-red-200'
                  }`}
                >
                  {resolveFeedback.type === 'success' ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                  ) : (
                    <AlertCircle className="w-4 h-4 shrink-0" />
                  )}
                  <span>{resolveFeedback.message}</span>
                </div>
              )}

              <p className="text-xs text-[#64748B] flex items-center gap-1.5">
                <HelpCircle className="w-3.5 h-3.5" />
                <span>Identifying your channel does not download anything by itself.</span>
              </p>
            </div>

            <div className="relative my-4 flex items-center justify-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-[#E2E8F0]" />
              </div>
              <span className="relative px-3 bg-white text-xs text-[#64748B] uppercase font-semibold">
                or
              </span>
            </div>

            <div className="p-4 rounded-xl border border-[#E2E8F0] bg-slate-50/50 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Video className="w-5 h-5 text-red-600" />
                  <div>
                    <span className="text-sm font-semibold text-[#0F172A]">
                      Connect YouTube (read-only)
                    </span>
                    <p className="text-xs text-[#64748B]">
                      Lets you pick your channel and enables owner analytics. It cannot post or change anything.
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleConnectOAuth}
                  disabled={submitting}
                >
                  {youtubeOAuthState === 'connected' ? 'Connected' : 'Connect'}
                </Button>
              </div>
            </div>

            <div className="pt-4 flex items-center justify-between">
              <Button
                variant="outline"
                onClick={() => setStepNumber(2)}
                leftIcon={<ArrowLeft className="w-4 h-4" />}
              >
                Back
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  onClick={handleSkipChannel}
                  disabled={submitting}
                >
                  Skip for now
                </Button>
                <Button
                  onClick={handleContinueChannel}
                  disabled={!channelInput.trim()}
                  isLoading={submitting}
                  rightIcon={<ArrowRight className="w-4 h-4" />}
                >
                  Continue
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Review */}
        {stepNumber === 4 && (
          <div className="p-6 sm:p-8 space-y-6">
            <div>
              <h1 className="text-xl font-semibold text-[#0F172A] tracking-tight">
                Review & Confirm
              </h1>
              <p className="text-sm text-[#64748B] mt-1">
                Confirm your content preferences before starting your strategist.
              </p>
            </div>

            <div className="divide-y divide-[#E2E8F0] border border-[#E2E8F0] rounded-xl overflow-hidden text-sm">
              {/* Niche row */}
              <div className="p-4 bg-white flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wider block mb-0.5">
                    Niche
                  </span>
                  <span className="font-medium text-[#0F172A]">
                    {niche || 'Not specified'}
                  </span>
                </div>
                <button
                  onClick={() => setStepNumber(1)}
                  className="text-xs font-semibold text-[#6366F1] hover:underline"
                >
                  Change
                </button>
              </div>

              {/* Tone row */}
              <div className="p-4 bg-white flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wider block mb-0.5">
                    Tone & Style
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-[#0F172A] capitalize">
                      {tonePreset || 'None'}
                    </span>
                    {toneInstructions && (
                      <span className="text-xs text-[#64748B] truncate max-w-xs">
                        ({toneInstructions})
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => setStepNumber(2)}
                  className="text-xs font-semibold text-[#6366F1] hover:underline"
                >
                  Change
                </button>
              </div>

              {/* Channel row */}
              <div className="p-4 bg-white flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wider block mb-0.5">
                    YouTube Channel
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-[#0F172A]">
                      {resolvedChannel?.title || resolvedChannel?.handle || resolvedChannel?.channel_id || 'None'}
                    </span>
                    {resolvedChannel ? (
                      resolvedChannel.verified ? (
                        <Badge variant="success" size="sm">Verified</Badge>
                      ) : (
                        <Badge variant="warning" size="sm">Unverified</Badge>
                      )
                    ) : (
                      <Badge variant="neutral" size="sm">None</Badge>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => setStepNumber(3)}
                  className="text-xs font-semibold text-[#6366F1] hover:underline"
                >
                  {resolvedChannel ? 'Change' : 'Add'}
                </button>
              </div>

              {/* YouTube Login Status */}
              <div className="p-4 bg-white flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wider block mb-0.5">
                    YouTube Login
                  </span>
                  <span className="font-medium text-[#0F172A] capitalize">
                    {youtubeOAuthState}
                  </span>
                </div>
                <Badge
                  variant={youtubeOAuthState === 'connected' ? 'success' : 'neutral'}
                  size="sm"
                >
                  {youtubeOAuthState === 'connected' ? 'Connected' : 'Disconnected'}
                </Badge>
              </div>

              {/* YouTube API Key Status */}
              <div className="p-4 bg-white flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wider block mb-0.5">
                    YouTube API Key
                  </span>
                  <span className="text-xs text-[#64748B]">
                    Read-only configuration from .env
                  </span>
                </div>
                <Badge
                  variant={apiKeyConfigured ? 'success' : 'warning'}
                  size="sm"
                >
                  {apiKeyConfigured ? 'Configured' : 'Not configured'}
                </Badge>
              </div>

              {/* Weekly Brief Schedule */}
              <div className="p-4 bg-white flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-[#64748B] uppercase tracking-wider block mb-0.5">
                    Weekly Brief Schedule
                  </span>
                  <div className="flex items-center gap-2 text-xs font-medium text-[#0F172A]">
                    <span className="capitalize">{settings?.brief_day || 'mon'}</span>
                    <span>at {settings?.brief_time || '08:00'}</span>
                    <span className="text-[#64748B]">({settings?.time_zone || 'Asia/Kolkata'})</span>
                  </div>
                </div>
                <Badge variant="info" size="sm">
                  Default schedule
                </Badge>
              </div>
            </div>

            <div className="pt-4 flex items-center justify-between">
              <Button
                variant="outline"
                onClick={() => setStepNumber(3)}
                leftIcon={<ArrowLeft className="w-4 h-4" />}
              >
                Back
              </Button>
              <Button
                onClick={handleFinishSetup}
                isLoading={submitting}
                rightIcon={<CheckCircle2 className="w-4 h-4" />}
              >
                Finish setup
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
