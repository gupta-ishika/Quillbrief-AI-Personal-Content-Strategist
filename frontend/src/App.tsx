import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sparkles, CheckCircle2 } from 'lucide-react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export const AppContent: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] flex flex-col justify-center items-center p-6">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-[#E2E8F0] p-8 text-center">
        <div className="inline-flex items-center justify-center w-12 h-12 bg-indigo-50 text-[#6366F1] rounded-full mb-4">
          <Sparkles className="w-6 h-6" />
        </div>
        <h1 className="text-2xl font-semibold text-[#0F172A] mb-2">
          AI Personal Content Strategist
        </h1>
        <p className="text-sm text-[#64748B] mb-6">
          Local, multi-agent strategist system for creators.
        </p>
        <div className="flex items-center justify-center gap-2 text-xs font-medium text-[#16A34A] bg-green-50 py-2 px-3 rounded-lg border border-green-200">
          <CheckCircle2 className="w-4 h-4" />
          <span>Frontend setup complete (React + TypeScript + Tailwind)</span>
        </div>
      </div>
    </div>
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
