import React, { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { apiClient } from './api/client';
import { HealthResponse } from './types';
import { AppLayout } from './components/layout/AppLayout';
import { TabId } from './components/layout/Sidebar';
import { OnboardingWizard } from './components/onboarding/OnboardingWizard';
import { HomeScreen } from './components/home/HomeScreen';
import { ApprovalsInbox } from './components/approvals/ApprovalsInbox';
import { SettingsScreen } from './components/settings/SettingsScreen';
import { PlaceholderScreen } from './components/common/PlaceholderScreen';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export const AppContent: React.FC = () => {
  const [checkingOnboarding, setCheckingOnboarding] = useState<boolean>(true);
  const [isOnboarded, setIsOnboarded] = useState<boolean>(false);
  const [currentTab, setCurrentTab] = useState<TabId>('home');
  const [targetApprovalId, setTargetApprovalId] = useState<string | null>(null);
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState<number>(0);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  // Initial onboarding & system check
  const checkInitialState = async () => {
    try {
      const [onb, healthData] = await Promise.all([
        apiClient.getOnboarding(),
        apiClient.getHealth().catch(() => null),
      ]);
      setIsOnboarded(onb.onboarding_completed);
      setHealth(healthData);

      if (onb.onboarding_completed) {
        updateApprovalsBadge();
      }
    } catch {
      // If server unreachable, assume onboarding incomplete or degraded
      setIsOnboarded(false);
    } finally {
      setCheckingOnboarding(false);
    }
  };

  const updateApprovalsBadge = async () => {
    try {
      const pending = await apiClient.listApprovals('PENDING');
      setPendingApprovalsCount(pending.length);
    } catch {
      // Ignore badge polling errors
    }
  };

  useEffect(() => {
    checkInitialState();
  }, []);

  // Poll approvals count periodically when onboarded
  useEffect(() => {
    if (!isOnboarded) return;

    const interval = setInterval(() => {
      updateApprovalsBadge();
    }, 10000);

    return () => clearInterval(interval);
  }, [isOnboarded]);

  const handleNavigateToApprovals = (approvalId?: string) => {
    if (approvalId) {
      setTargetApprovalId(approvalId);
    }
    setCurrentTab('approvals');
    updateApprovalsBadge();
  };

  if (checkingOnboarding) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex flex-col items-center justify-center p-6 text-[#64748B]">
        <Loader2 className="w-8 h-8 animate-spin text-[#6366F1] mb-3" />
        <p className="text-sm">Connecting to local strategist...</p>
      </div>
    );
  }

  // First-run onboarding wizard replaces app shell entirely
  if (!isOnboarded) {
    return (
      <OnboardingWizard
        onCompleted={() => {
          setIsOnboarded(true);
          setCurrentTab('home');
          updateApprovalsBadge();
        }}
      />
    );
  }

  return (
    <AppLayout
      currentTab={currentTab}
      onTabChange={(tab) => {
        setCurrentTab(tab);
        updateApprovalsBadge();
      }}
      pendingApprovalsCount={pendingApprovalsCount}
      health={health}
    >
      {currentTab === 'home' && (
        <HomeScreen onNavigateToApprovals={handleNavigateToApprovals} />
      )}
      {currentTab === 'approvals' && (
        <ApprovalsInbox
          initialApprovalId={targetApprovalId}
          onClearInitialApprovalId={() => setTargetApprovalId(null)}
        />
      )}
      {currentTab === 'briefs' && (
        <PlaceholderScreen
          title="Weekly Briefs"
          description="Curated strategic briefings scheduled weekly based on audience comment trends."
          phase="Phase 3"
        />
      )}
      {currentTab === 'library' && (
        <PlaceholderScreen
          title="Drafts Library"
          description="Review ready-to-post scripts, descriptions, and repurposed social posts."
          phase="Phase 2"
        />
      )}
      {currentTab === 'insights' && (
        <PlaceholderScreen
          title="Audience Insights"
          description="Extracted comment themes, sentiment patterns, and analyst findings."
          phase="Phase 4"
        />
      )}
      {currentTab === 'runs' && (
        <PlaceholderScreen
          title="Execution Runs"
          description="Supervisor routing history, task lists, and token usage timelines."
          phase="Phase 3"
        />
      )}
      {currentTab === 'settings' && <SettingsScreen />}
    </AppLayout>
  );
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
};

export default App;
