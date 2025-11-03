'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Section from './Section';
import { terminalScenes, TerminalScene, captions } from '@/lib/terminalScenes';

interface QuietTerminalProps {
  open: boolean;
  onClose: () => void;
}

export default function QuietTerminal({ open, onClose }: QuietTerminalProps) {
  const [currentSceneId, setCurrentSceneId] = useState('handoff-workflow');
  const [currentLineIndex, setCurrentLineIndex] = useState(0);
  const [displayedText, setDisplayedText] = useState('');
  const [isPlaying, setIsPlaying] = useState(true);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  const currentScene = terminalScenes.find((s: TerminalScene) => s.id === currentSceneId) || terminalScenes[0];
  const lines = currentScene.lines;
  const maxVisibleLines = 8;

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);

    const handleChange = (e: MediaQueryListEvent) => {
      setPrefersReducedMotion(e.matches);
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      setCurrentLineIndex(0);
      setDisplayedText('');
      setIsPlaying(true);
      return;
    }

    if (prefersReducedMotion) {
      setCurrentLineIndex(lines.length);
      setDisplayedText('');
      return;
    }

    if (!isPlaying || currentLineIndex >= lines.length) return;

    const currentLine = lines[currentLineIndex];

    if (displayedText.length < currentLine.length) {
      const timeout = setTimeout(() => {
        setDisplayedText(currentLine.substring(0, displayedText.length + 1));
      }, 35);
      return () => clearTimeout(timeout);
    } else {
      const isBallFlip = currentLine.includes('Ball →');
      const timeout = setTimeout(
        () => {
          setCurrentLineIndex(currentLineIndex + 1);
          setDisplayedText('');
        },
        isBallFlip ? 700 : 150
      );
      return () => clearTimeout(timeout);
    }
  }, [currentLineIndex, displayedText, isPlaying, lines, prefersReducedMotion, open]);

  useEffect(() => {
    setCurrentLineIndex(0);
    setDisplayedText('');
    setIsPlaying(true);
  }, [currentSceneId]);

  const handleSceneChange = (sceneId: string) => {
    setCurrentSceneId(sceneId);
  };

  if (!open) return null;

  const displayedLines = lines.slice(0, currentLineIndex);
  const visibleLines = displayedLines.slice(-maxVisibleLines);

  const isBallFlipLine = (line: string) => line.includes('Ball →');
  
  const getLineClass = (line: string) => {
    if (line.startsWith('#')) return 'line-comment';
    if (line.includes('Ball →')) return 'line-ball';
    if (line.startsWith('Status:') || line.startsWith('Found:') || line.includes('Thread persisted:') || line.includes('Searchable history')) return 'line-status';
    return '';
  };
  
  const currentCaption = captions[currentSceneId] || '';

  return (
    <Section className="py-12 md:py-16">
      {currentCaption && (
        <div className="text-center mb-6 text-secondary text-sm md:text-base max-w-2xl mx-auto">
          {currentCaption}
        </div>
      )}
      <div className="mx-auto w-full rounded-xl ring-1 ring-border bg-surface shadow-md group">
        <div className="flex items-center justify-between px-6 py-3 border-b border-border/50">
          <div className="text-xs text-secondary font-medium">Terminal Demo</div>
          <div className="flex items-center gap-2">
            <select
              value={currentSceneId}
              onChange={(e) => handleSceneChange(e.target.value)}
              className="text-xs px-3 py-1.5 rounded-md ring-1 ring-border bg-background text-primary cursor-pointer hover:ring-accent transition-colors"
            >
              {terminalScenes.map((scene: TerminalScene) => (
                <option key={scene.id} value={scene.id}>
                  {scene.title}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div
          className="relative h-[300px] md:h-[350px] overflow-hidden"
          style={{
            maskImage: 'linear-gradient(to bottom, #000, #000 92%, transparent)',
            WebkitMaskImage: 'linear-gradient(to bottom, #000, #000 92%, transparent)',
          }}
        >
          <div className="p-8 space-y-2 leading-relaxed font-mono text-sm">
            {visibleLines.map((line: string, index: number) => {
              const isCommand = line.startsWith('$');
              const isBallFlip = isBallFlipLine(line);
              const lineClass = getLineClass(line);

              return (
                <motion.div
                  key={index}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className={`flex items-start gap-2 ${lineClass}`}
                >
                  {isBallFlip && (
                    <motion.div
                      initial={{ scaleY: 0 }}
                      animate={{ scaleY: 1 }}
                      transition={{ duration: 0.3 }}
                      className="w-0.5 h-5 bg-accent rounded shrink-0"
                    />
                  )}
                  {isCommand && <span className="text-accent shrink-0">$</span>}
                  <span className={isCommand ? 'text-primary' : 'text-secondary pl-3'}>
                    {line.replace('$ ', '')}
                  </span>
                </motion.div>
              );
            })}

            {currentLineIndex < lines.length && displayedText && (
              <div className={`flex items-start gap-2 ${getLineClass(lines[currentLineIndex])}`}>
                {isBallFlipLine(lines[currentLineIndex]) && (
                  <motion.div
                    initial={{ scaleY: 0 }}
                    animate={{ scaleY: 1 }}
                    transition={{ duration: 0.3 }}
                    className="w-0.5 h-5 bg-accent rounded shrink-0"
                  />
                )}
                {lines[currentLineIndex].startsWith('$') && <span className="text-accent shrink-0">$</span>}
                <span className={lines[currentLineIndex].startsWith('$') ? 'text-primary' : 'text-secondary pl-3'}>
                  {displayedText.replace('$ ', '')}
                </span>
                {!prefersReducedMotion && isPlaying && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity }}
                    className="inline-block w-1.5 h-4 bg-accent ml-0.5"
                  />
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </Section>
  );
}
