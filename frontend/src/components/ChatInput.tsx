import React, { forwardRef, memo, useCallback, useEffect, useRef } from 'react';
import { MicIcon, SendIcon, StopIcon, CloseIcon, CheckIcon } from './Icons';

interface ChatInputProps {
  message: string;
  isStreaming: boolean;
  isRecording?: boolean;
  speechUnavailable: boolean;
  speechState: string;
  locale: string;
  onMessageChange: (value: string) => void;
  onSend: (text?: string) => void;
  onMicClick: () => void;
  onStop: () => void;
  onCancelRecording?: () => void;
}

const PLACEHOLDERS: Record<string, string> = {
  en: 'Ask about Physics, Chemistry, Biology, or Math...',
  lg: 'Buuza ku Physics, Chemistry, Biology, oba Math...',
  sw: 'Uliza kuhusu Fizikia, Kemia, Biolojia, au Hesabu...',
  nyn: 'Buuza omu Physics, Chemistry, Biology, nari Math...',
};

/** Inline waveform — 5 animated bars */
function InlineWaveform() {
  return (
    <div className="composer-waveform" aria-hidden="true">
      <span /><span /><span /><span /><span />
    </div>
  );
}

const ChatInput = memo(forwardRef<HTMLTextAreaElement, ChatInputProps>(
  function ChatInputInner(
    { message, isStreaming, isRecording, speechUnavailable, speechState, locale, onMessageChange, onSend, onMicClick, onStop, onCancelRecording },
    ref,
  ) {
    const localRef = useRef<HTMLTextAreaElement | null>(null);
    const setRef = useCallback((el: HTMLTextAreaElement | null) => {
      localRef.current = el;
      if (typeof ref === 'function') ref(el);
      else if (ref) (ref as React.MutableRefObject<HTMLTextAreaElement | null>).current = el;
    }, [ref]);

    // Auto-resize
    useEffect(() => {
      const ta = localRef.current;
      if (!ta) return;
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
    }, [message]);

    // ── Recording state: inline waveform + cancel/confirm ──
    if (isRecording) {
      return (
        <div className="composer composer-active-recording">
          <div className="composer-rec-label">
            <span className="composer-rec-dot" aria-hidden="true" />
            Listening...
          </div>
          <div className="composer-rec-controls">
            <InlineWaveform />
            <button
              className="composer-rec-cancel"
              onClick={onCancelRecording ?? onMicClick}
              aria-label="Cancel recording"
            >
              <CloseIcon />
            </button>
            <button
              className="composer-rec-confirm"
              onClick={onMicClick}
              aria-label="Send recording"
            >
              <CheckIcon />
            </button>
          </div>
        </div>
      );
    }

    // ── Normal state ──
    return (
      <div className="composer">
        <textarea
          ref={setRef}
          className="input"
          id="composer-input"
          aria-label="Type your question"
          placeholder={PLACEHOLDERS[locale] ?? PLACEHOLDERS.en}
          value={message}
          rows={1}
          onChange={(e) => {
            if (e.target.value.length <= 2000) onMessageChange(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); }
          }}
          style={{ resize: 'none', overflow: 'hidden' }}
        />
        <button
          className={`composer-circle-btn mic-circle-btn ${speechState === 'listening' ? 'btn-recording' : ''}`}
          onClick={onMicClick}
          disabled={speechUnavailable || isStreaming}
          aria-label={speechState === 'listening' ? 'Stop listening' : 'Start speaking'}
        >
          <MicIcon />
        </button>
        <button
          className={`composer-circle-btn send-circle-btn ${isStreaming ? 'send-btn-stop' : ''}`}
          onClick={isStreaming ? onStop : () => onSend()}
          disabled={!isStreaming && !message.trim()}
          aria-label={isStreaming ? 'Stop response' : 'Send message'}
        >
          {isStreaming ? <StopIcon /> : <SendIcon />}
        </button>
      </div>
    );
  },
));

ChatInput.displayName = 'ChatInput';
export default ChatInput;
