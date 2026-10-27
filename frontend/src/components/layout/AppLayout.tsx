import React from 'react';
import { Sidebar, TabId } from './Sidebar';
import { HealthResponse } from '../../types';

export interface AppLayoutProps {
  currentTab: TabId;
  onTabChange: (tab: TabId) => void;
  pendingApprovalsCount?: number;
  health?: HealthResponse | null;
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  currentTab,
  onTabChange,
  pendingApprovalsCount = 0,
  health,
  children,
}) => {
  return (
    <div className="min-h-screen bg-[#F8FAFC] flex text-[#0F172A]">
      <Sidebar
        currentTab={currentTab}
        onTabChange={onTabChange}
        pendingApprovalsCount={pendingApprovalsCount}
        health={health}
      />
      <main className="flex-1 pb-20 md:pb-8 overflow-y-auto">
        <div className="max-w-[1100px] mx-auto p-4 sm:p-6 lg:p-8">
          {children}
        </div>
      </main>
    </div>
  );
};
