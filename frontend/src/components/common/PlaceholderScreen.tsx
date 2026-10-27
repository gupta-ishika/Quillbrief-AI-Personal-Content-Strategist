import React from 'react';
import { Sparkles } from 'lucide-react';
import { Card } from './Card';
import { Badge } from './Badge';

export interface PlaceholderScreenProps {
  title: string;
  description: string;
  phase: string;
}

export const PlaceholderScreen: React.FC<PlaceholderScreenProps> = ({
  title,
  description,
  phase,
}) => {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between pb-4 border-b border-[#E2E8F0]">
        <div>
          <h1 className="text-2xl font-semibold text-[#0F172A] tracking-tight">
            {title}
          </h1>
          <p className="text-sm text-[#64748B] mt-1">{description}</p>
        </div>
        <Badge variant="primary" size="md">
          {phase}
        </Badge>
      </div>

      <Card className="py-16 text-center">
        <div className="w-12 h-12 rounded-full bg-indigo-50 text-[#6366F1] flex items-center justify-center mx-auto mb-3">
          <Sparkles className="w-6 h-6" />
        </div>
        <h3 className="text-base font-semibold text-[#0F172A] mb-1">
          {title} Screen
        </h3>
        <p className="text-xs text-[#64748B] max-w-sm mx-auto">
          This module is part of {phase}. Strategy goal decomposition, human approval workflows, and first-run onboarding are active.
        </p>
      </Card>
    </div>
  );
};
