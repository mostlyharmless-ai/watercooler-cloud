'use client';

import { useState } from 'react';
import Header from '@/components/Header';
import Hero from '@/components/Hero';
import QuietTerminal from '@/components/QuietTerminal';
import Problem from '@/components/Problem';
import Solution from '@/components/Solution';
import Quickstart from '@/components/Quickstart';
import Footer from '@/components/Footer';

export default function Page() {
  const [terminalOpen, setTerminalOpen] = useState(false);
  
  return (
    <div className="bg-background min-h-screen">
      <Header />
      <Hero 
        onToggleTerminal={() => setTerminalOpen(!terminalOpen)} 
        terminalOpen={terminalOpen}
      />
      <QuietTerminal 
        open={terminalOpen} 
        onClose={() => setTerminalOpen(false)}
      />
      <div style={{ marginTop: '5rem', marginBottom: '5rem' }}>
        <Problem />
      </div>
      <div style={{ marginBottom: '5rem' }}>
        <Solution />
      </div>
      <div style={{ marginBottom: '5rem' }}>
        <Quickstart />
      </div>
      <Footer />
    </div>
  );
}
