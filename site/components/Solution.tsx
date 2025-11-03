import React from 'react';
import { copy } from '@/lib/copy';
import { Check } from 'lucide-react';

export default function Solution() {
  return (
    <div className="animate-fade-in-up" style={{ maxWidth: '56rem', margin: '0 auto', padding: '0 1.5rem', animationDelay: '0.1s', opacity: 0 }}>
      <div style={{ padding: '2rem 2rem' }}>
        <h2 className="text-2xl md:text-3xl text-primary font-semibold tracking-tight" style={{ marginBottom: '4rem' }}>The solution</h2>
        <ul className="grid max-w-2xl" style={{ gap: '1.5rem' }}>
          {copy.solution.bullets.map((bullet, index) => (
            <li key={index} className="flex items-start group" style={{ gap: '0.75rem' }}>
              <div className="flex items-center justify-center shrink-0 group-hover:bg-accent/20 transition-colors" style={{ width: '2.5rem', height: '2.5rem', borderRadius: '0.5rem', background: 'rgba(13, 148, 136, 0.1)' }}>
                <Check className="text-accent" strokeWidth={2.5} style={{ width: '1.25rem', height: '1.25rem' }} />
              </div>
              <span className="text-secondary leading-relaxed" style={{ fontSize: '1.125rem', paddingTop: '0.5rem' }}>{bullet}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
