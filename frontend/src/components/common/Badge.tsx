import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'primary' | 'success' | 'warning' | 'error' | 'info' | 'neutral';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  size = 'md',
  className = '',
}) => {
  const variantStyles = {
    primary: 'bg-indigo-50 text-[#6366F1] border-indigo-200',
    success: 'bg-green-50 text-[#16A34A] border-green-200',
    warning: 'bg-amber-50 text-[#D97706] border-amber-200',
    error: 'bg-red-50 text-[#DC2626] border-red-200',
    info: 'bg-blue-50 text-[#2563EB] border-blue-200',
    neutral: 'bg-slate-100 text-[#64748B] border-slate-200',
  };

  const sizeStyles = {
    sm: 'text-[11px] px-2 py-0.5',
    md: 'text-xs px-2.5 py-1',
  };

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full border ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
    >
      {children}
    </span>
  );
};
