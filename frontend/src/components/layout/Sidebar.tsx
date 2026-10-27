import React from 'react';
import {
  Sparkles,
  Inbox,
  FileText,
  BookOpen,
  LineChart,
  History,
  Settings,
} from 'lucide-react';
import { HealthResponse } from '../../types';

export type TabId =
  | 'home'
  | 'approvals'
  | 'briefs'
  | 'library'
  | 'insights'
  | 'runs'
  | 'settings';

export interface SidebarProps {
  currentTab: TabId;
  onTabChange: (tab: TabId) => void;
  pendingApprovalsCount?: number;
  health?: HealthResponse | null;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onTabChange,
  pendingApprovalsCount = 0,
  health,
}) => {
  const navItems: Array<{
    id: TabId;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    badge?: number;
  }> = [
    { id: 'home', label: 'Home', icon: Sparkles },
    {
      id: 'approvals',
      label: 'Approvals',
      icon: Inbox,
      badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : undefined,
    },
    { id: 'briefs', label: 'Briefs', icon: FileText },
    { id: 'library', label: 'Library', icon: BookOpen },
    { id: 'insights', label: 'Insights', icon: LineChart },
    { id: 'runs', label: 'Runs', icon: History },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <>
      {/* Desktop & Tablet Sidebar */}
      <aside className="hidden md:flex flex-col w-20 lg:w-64 bg-white border-r border-[#E2E8F0] h-screen sticky top-0 shrink-0 z-30 transition-all duration-200">
        {/* Brand header */}
        <div className="p-4 lg:p-6 border-b border-[#E2E8F0] flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-[#6366F1] shrink-0">
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="hidden lg:block truncate">
            <h1 className="font-semibold text-sm text-[#0F172A] tracking-tight truncate">
              Quillbrief AI
            </h1>
            <p className="text-[11px] text-[#64748B] truncate">Content Strategist</p>
          </div>
        </div>

        {/* Navigation list */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                aria-current={isActive ? 'page' : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors cursor-pointer select-none relative ${
                  isActive
                    ? 'bg-indigo-50/80 text-[#6366F1]'
                    : 'text-[#64748B] hover:text-[#0F172A] hover:bg-slate-50'
                }`}
                title={item.label}
              >
                <Icon className={`w-5 h-5 shrink-0 ${isActive ? 'text-[#6366F1]' : 'text-[#64748B]'}`} />
                <span className="hidden lg:inline-block flex-1 text-left truncate">
                  {item.label}
                </span>

                {item.badge !== undefined && (
                  <span
                    className={`inline-flex items-center justify-center text-xs font-semibold rounded-full min-w-5 h-5 px-1.5 ${
                      isActive
                        ? 'bg-[#6366F1] text-white'
                        : 'bg-indigo-100 text-[#6366F1]'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Health status footer */}
        <div className="p-3 lg:p-4 border-t border-[#E2E8F0] bg-slate-50/50">
          <div className="flex items-center gap-2.5">
            <div className="shrink-0">
              {health?.status === 'healthy' ? (
                <div className="w-2.5 h-2.5 rounded-full bg-[#16A34A] ring-4 ring-green-100" />
              ) : health?.status === 'degraded' ? (
                <div className="w-2.5 h-2.5 rounded-full bg-[#D97706] ring-4 ring-amber-100" />
              ) : (
                <div className="w-2.5 h-2.5 rounded-full bg-slate-300" />
              )}
            </div>
            <div className="hidden lg:block text-xs truncate">
              <span className="font-medium text-[#0F172A]">
                {health?.status === 'healthy' ? 'System ready' : health?.status === 'degraded' ? 'Degraded state' : 'Connecting...'}
              </span>
              <p className="text-[11px] text-[#64748B] truncate">
                {health?.ollama_reachable ? 'Ollama connected' : 'Ollama offline'}
              </p>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-[#E2E8F0] z-40 flex items-center justify-around px-2 py-2 shadow-lg">
        {navItems.slice(0, 5).map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`flex flex-col items-center justify-center p-1.5 rounded-lg text-[10px] font-medium relative ${
                isActive ? 'text-[#6366F1]' : 'text-[#64748B]'
              }`}
            >
              <Icon className="w-5 h-5 mb-0.5" />
              <span>{item.label}</span>
              {item.badge !== undefined && (
                <span className="absolute top-1 right-2 w-4 h-4 rounded-full bg-[#6366F1] text-white text-[9px] flex items-center justify-center font-bold">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </>
  );
};
