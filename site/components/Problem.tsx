import React from 'react';
import { copy } from '@/lib/copy';
import { AlertCircle, Shuffle, Database } from 'lucide-react';

const icons = [AlertCircle, Shuffle, Database];

export default function Problem() {
  return (
    <div className="animate-fade-in-up" style={{ maxWidth: '56rem', margin: '0 auto', padding: '0 1.5rem' }}>
      <div className="card-hover" style={{ background: '#FFFFFF', borderRadius: '1rem', padding: '2rem 2rem', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.03)', transition: 'all 0.3s ease' }}>
        <h2 className="text-2xl md:text-3xl text-primary font-semibold tracking-tight" style={{ marginBottom: '4rem' }}>The problem</h2>
        <ul className="grid max-w-2xl" style={{ gap: '1.5rem' }}>
          {copy.problem.bullets.map((bullet, index) => {
            const Icon = icons[index];
            return (
              <li key={index} className="flex items-start group" style={{ gap: '0.75rem' }}>
                <div className="flex items-center justify-center shrink-0 group-hover:bg-accent/20 transition-colors" style={{ width: '2.5rem', height: '2.5rem', borderRadius: '0.5rem', background: 'rgba(13, 148, 136, 0.1)' }}>
                  <Icon className="text-accent" strokeWidth={1.5} style={{ width: '1.25rem', height: '1.25rem' }} />
                </div>
                <p className="leading-relaxed" style={{ fontSize: '1.125rem', paddingTop: '0.5rem' }}>
                  <strong className="text-primary font-semibold">{bullet.title}</strong>{' '}
                  <span className="text-secondary">— {bullet.description}</span>
                </p>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
