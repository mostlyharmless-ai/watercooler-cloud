import React from 'react';
import Container from './Container';

interface SectionProps {
  children: React.ReactNode;
  className?: string;
  id?: string;
}

export default function Section({ id, className = '', children }: SectionProps) {
  return (
    <section id={id} className={`py-20 md:py-32 lg:py-40 ${className}`}>
      <Container>{children}</Container>
    </section>
  );
}
