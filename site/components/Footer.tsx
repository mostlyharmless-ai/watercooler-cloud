import React from 'react';
import Container from './Container';
import { copy, urls } from '@/lib/copy';
import { Twitter } from 'lucide-react';

export default function Footer() {
  return (
    <footer className="py-20 md:py-24 text-center">
      <Container>
        <div className="text-sm text-secondary">{copy.footer.tagline}</div>
        <div className="mt-6 flex justify-center">
          <a
            href={urls.twitter}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="X"
            className="text-secondary hover:text-accent transition-colors"
          >
            <Twitter className="w-6 h-6" />
          </a>
        </div>
      </Container>
    </footer>
  );
}
