import React from 'react';
import { copy, urls } from '@/lib/copy';

export default function Quickstart() {
  return (
    <div className="animate-fade-in-up" style={{ maxWidth: '56rem', margin: '0 auto', padding: '0 1.5rem', animationDelay: '0.2s', opacity: 0 }}>
      <div className="card-hover" style={{ background: '#FFFFFF', borderRadius: '1rem', padding: '2rem 2rem', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.03)', transition: 'all 0.3s ease' }}>
        <h2 className="text-2xl md:text-3xl mb-8 text-primary font-semibold tracking-tight">Install MCP server</h2>
        <pre className="rounded-xl ring-1 ring-border bg-code-bg p-6 text-sm md:text-base leading-7 font-mono overflow-x-auto text-primary shadow-sm hover:ring-accent/50 transition-all">
          {copy.quickstart.code}
        </pre>
      </div>
    </div>
  );
}
