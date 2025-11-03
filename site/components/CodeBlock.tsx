'use client';

import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CodeBlockProps {
  code: string;
  language?: string;
  className?: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ code, language = 'bash', className }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={cn('relative group', className)}>
      <div className="absolute right-3 top-3 z-10">
        <button
          onClick={handleCopy}
          className="flex items-center gap-2 px-3 py-1.5 bg-surface border border-border rounded-md text-sm text-text-secondary hover:text-text-primary hover:border-accent/50 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-focus-ring"
          aria-label={copied ? 'Copied!' : 'Copy code'}
        >
          {copied ? (
            <>
              <Check className="w-4 h-4" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-4 h-4" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="bg-code-bg border border-border rounded-lg p-6 overflow-x-auto">
        <code className={cn('font-mono text-sm text-text-primary', `language-${language}`)}>
          {code}
        </code>
      </pre>
    </div>
  );
};
