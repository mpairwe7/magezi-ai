import React, { memo, useCallback, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { SubjectInfo } from '../hooks/useApi';
import { useFeedback } from '../hooks/useApi';
import { isSpeaking, stopSpeaking, useTtsMutation } from '../hooks/useSpeech';
import { getSubjectInfo } from '../lib/subjects';
import { ChatTurn } from '../store/useChatStore';
import {
  BotIcon,
  CheckIcon,
  CopyIcon,
  LoadingDots,
  RefreshIcon,
  SpeakerIcon,
  SparklesIcon,
  StopIcon,
  ThumbDownIcon,
  ThumbUpIcon,
  UserIcon,
} from './Icons';

interface ChatMessageProps {
  turn: ChatTurn;
  locale: string;
  subjects?: SubjectInfo[];
  canRetry?: boolean;
  onRetry?: (turnId: string) => void;
}

function normaliseMarkdown(text: string): string {
  let md = text
    // Ensure blank line before headings
    .replace(/([^\n])(#{1,4}\s)/g, '$1\n\n$2')
    .replace(/(#{1,4}\s[^\n]{3,}?)([A-Z][a-z])/g, (_, header, next) => (
      header.length < 80 ? `${header}\n${next}` : `${header}${next}`
    ))
    // Ensure blank line before lists
    .replace(/([^\n-*\s])\n([-*]\s)/g, '$1\n\n$2')
    .replace(/([^\n\d])\n(\d+\.\s)/g, '$1\n\n$2')
    // Ensure blank line before code blocks
    .replace(/([^\n])\n(```)/g, '$1\n\n$2')
    // Break before bold headings
    .replace(/([.!?])\s*(\*\*[A-Z])/g, '$1\n\n$2')
    // Normalise multiple newlines
    .replace(/\n{3,}/g, '\n\n');

  // Auto-split long flat paragraphs at sentence boundaries for readability
  const blocks = md.split('\n\n');
  const result: string[] = [];
  for (const block of blocks) {
    const trimmed = block.trim();
    // Only split plain paragraphs (not headings, lists, code, etc.)
    if (trimmed.length > 200 && !trimmed.startsWith('#') && !trimmed.startsWith('-') &&
        !trimmed.startsWith('*') && !trimmed.startsWith('`') && !trimmed.startsWith('>') &&
        !/^\d+\./.test(trimmed)) {
      const sentences: string[] = [];
      let buf = '';
      for (const part of trimmed.split(/(?<=[.!?])\s+/)) {
        if (!buf) { buf = part; }
        else if (buf.length + part.length < 180) { buf += ' ' + part; }
        else { sentences.push(buf); buf = part; }
      }
      if (buf) sentences.push(buf);
      result.push(sentences.join('\n\n'));
    } else {
      result.push(trimmed);
    }
  }

  return result.join('\n\n');
}

function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  const normalized = clean.length === 3
    ? clean.split('').map((char) => `${char}${char}`).join('')
    : clean;
  const value = Number.parseInt(normalized, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function ChatMessageInner({
  turn,
  locale,
  subjects,
  canRetry = false,
  onRetry,
}: ChatMessageProps) {
  const isAssistant = turn.role === 'assistant';
  const isGreeting = turn.id === 'greeting-0';
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [playing, setPlaying] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [copied, setCopied] = useState(false);
  const feedbackMutation = useFeedback();
  const ttsMutation = useTtsMutation();
  const subjectInfo = getSubjectInfo(turn.subject, subjects);
  const isLong = turn.content.length > 1500;

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(turn.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable.
    }
  }, [turn.content]);

  const handleListen = useCallback(async () => {
    if (playing || isSpeaking()) {
      stopSpeaking();
      setPlaying(false);
      return;
    }
    setPlaying(true);
    try {
      await ttsMutation.mutateAsync({ text: turn.content, locale });
    } catch {
      // Silent TTS failure keeps the UI lightweight.
    } finally {
      setPlaying(false);
    }
  }, [locale, playing, ttsMutation, turn.content]);

  const handleFeedback = useCallback((rating: 'up' | 'down') => {
    const nextRating = feedback === rating ? null : rating;
    setFeedback(nextRating);
    if (nextRating) {
      feedbackMutation.mutate({
        message_id: turn.id,
        rating: nextRating,
        user_query: '',
        bot_reply: turn.content.slice(0, 500),
      });
    }
  }, [feedback, feedbackMutation, turn.content, turn.id]);

  return (
    <article
      className="message-row"
      role="article"
      aria-label={`${turn.role === 'user' ? 'You' : 'Magezi'}: ${turn.content.slice(0, 60)}`}
    >
      <div className={`avatar ${turn.role}`} aria-hidden="true">
        {turn.role === 'user' ? <UserIcon /> : <BotIcon />}
      </div>
      <div className={`bubble ${turn.role}`}>
        <span className="bubble-role">
          {turn.role === 'user' ? 'you' : 'magezi'}
          {isAssistant && turn.subject && subjectInfo && (
            <span
              className="bubble-subject"
              style={{
                background: hexToRgba(subjectInfo.color, 0.14),
                border: `1px solid ${hexToRgba(subjectInfo.color, 0.32)}`,
                color: subjectInfo.color,
              }}
            >
              {subjectInfo.name}
            </span>
          )}
        </span>

        <div className={`msg-content ${isLong && !expanded ? 'msg-collapsed' : ''}`}>
          {isAssistant ? (
            <Markdown remarkPlugins={[remarkGfm]}>
              {normaliseMarkdown(turn.content)}
            </Markdown>
          ) : (
            turn.content
          )}
        </div>

        {isAssistant && isLong && (
          <button
            className="expand-btn"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            {expanded ? 'Show less' : 'Show full response'}
          </button>
        )}

        {isAssistant && !isGreeting && turn.groundingWarning && (
          <div className="alert-banner alert-warn" role="alert">
            Verify this answer with your teacher. Retrieval confidence was low.
          </div>
        )}

        {isAssistant && !isGreeting && turn.escalationRequired && (
          <div className="alert-banner alert-danger" role="alert">
            This topic is outside Magezi&apos;s supported A-Level STEM scope.
          </div>
        )}

        {isAssistant && turn.citations && turn.citations.length > 0 && (
          <details className="citations">
            <summary>
              <SparklesIcon /> Syllabus Sources ({turn.citations.length})
              {turn.faithfulnessScore != null && (
                <span
                  className={turn.faithfulnessScore >= 0.6 ? 'grounding-ok' : 'grounding-warn'}
                >
                  {turn.faithfulnessScore >= 0.6 ? ' Well grounded' : ' Verify with teacher'}
                </span>
              )}
            </summary>
            <ol>
              {turn.citations.map((citation) => {
                const citationSubject = getSubjectInfo(citation.subject, subjects);
                return (
                  <li key={citation.ref}>
                    <strong>{citation.source}</strong>
                    {citationSubject && (
                      <span
                        className="cite-subject"
                        style={{
                          background: hexToRgba(citationSubject.color, 0.14),
                          border: `1px solid ${hexToRgba(citationSubject.color, 0.28)}`,
                          color: citationSubject.color,
                        }}
                      >
                        {citationSubject.name}
                      </span>
                    )}
                    {citation.topic && ` - ${citation.topic}`}
                    {citation.section && ` > ${citation.section}`}
                    {citation.page && ` p.${citation.page}`}
                    {citation.year && ` (UNEB ${citation.year})`}
                    {citation.passage && (
                      <div className="cite-passage">
                        {citation.passage.slice(0, 200)}
                        {citation.passage.length > 200 ? '...' : ''}
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          </details>
        )}

        {isAssistant && !isGreeting && turn.content && (
          <div className="bubble-actions">
            <button
              className={`action-btn ${copied ? 'action-btn-ok' : ''}`}
              onClick={handleCopy}
              aria-label={copied ? 'Copied' : 'Copy response'}
              title={copied ? 'Copied' : 'Copy'}
            >
              {copied ? <><CheckIcon /> Copied</> : <><CopyIcon /> Copy</>}
            </button>
            {onRetry && canRetry && (
              <button
                className="action-btn"
                onClick={() => onRetry(turn.id)}
                aria-label="Retry latest response"
                title="Retry latest response"
              >
                <RefreshIcon /> Retry
              </button>
            )}
            <button
              className={`action-btn ${playing ? 'action-btn-active' : ''}`}
              onClick={handleListen}
              disabled={ttsMutation.isPending && !playing}
              aria-label={playing ? 'Stop listening' : 'Listen to response'}
              title={playing ? 'Stop' : 'Listen'}
            >
              {ttsMutation.isPending && !playing
                ? <LoadingDots />
                : playing
                  ? <><StopIcon /> Stop</>
                  : <><SpeakerIcon /> Listen</>}
            </button>
            <div className="feedback-row" role="group" aria-label="Rate this response">
              <button
                className={`feedback-btn ${feedback === 'up' ? 'active-up' : ''}`}
                onClick={() => handleFeedback('up')}
                aria-label="Helpful"
                aria-pressed={feedback === 'up'}
              >
                <ThumbUpIcon />
              </button>
              <button
                className={`feedback-btn ${feedback === 'down' ? 'active-down' : ''}`}
                onClick={() => handleFeedback('down')}
                aria-label="Not helpful"
                aria-pressed={feedback === 'down'}
              >
                <ThumbDownIcon />
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

export default memo(ChatMessageInner);
