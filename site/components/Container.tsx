import React from 'react';

interface ContainerProps {
  children: React.ReactNode;
  className?: string;
}

export default function Container({ className = '', children }: ContainerProps) {
  return (
    <div className={`mx-auto w-full max-w-[var(--page-max)] px-6 md:px-8 ${className}`}>
      {children}
    </div>
  );
}
