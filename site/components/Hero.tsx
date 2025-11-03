'use client';

import React from 'react';
import Container from './Container';
import { copy, urls } from '@/lib/copy';

interface HeroProps {
  onToggleTerminal: () => void;
  terminalOpen: boolean;
}

export default function Hero({ onToggleTerminal, terminalOpen }: HeroProps) {
  return (
    <section className="pb-16 md:pb-20" style={{ paddingTop: '4rem' }}>
      <Container className="text-center">
        <h1 className="mx-auto max-w-[24ch] text-primary">
          {copy.hero.headline}
        </h1>
        <p className="mx-auto mt-8 max-w-[60ch] text-lg md:text-xl text-secondary leading-relaxed">
          {copy.hero.subheadline}
        </p>

        <button
          onClick={onToggleTerminal}
          className="mt-12 text-sm text-secondary hover:text-accent inline-flex items-center gap-2 no-underline transition-colors"
        >
          {terminalOpen ? '▾ Hide demo' : '▶ See it in action'}
        </button>
      </Container>
    </section>
  );
}
