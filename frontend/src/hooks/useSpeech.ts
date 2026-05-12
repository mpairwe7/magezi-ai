/**
 * Speech hooks — TanStack Query wrappers for voice operations.
 *
 * Uses client-side Web Speech Synthesis API for TTS (no backend needed).
 * Provides mutation hooks for consistent loading/error state management.
 */

import { useMutation } from '@tanstack/react-query';
import { speak, stopSpeaking, isTtsAvailable, initVoices } from '../services/voiceService';
import { useEffect, useState } from 'react';

/** Check TTS availability (resolves after voices load). */
export function useTtsAvailable() {
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    initVoices().then(() => {
      setAvailable(isTtsAvailable());
    });
  }, []);

  return available;
}

/** TTS mutation — speak text aloud. Manages loading/playing state. */
export function useTtsMutation() {
  return useMutation<void, Error, { text: string; locale: string }>({
    mutationFn: ({ text, locale }) => speak(text, locale),
    onMutate: () => {
      // Cancel any ongoing speech before starting new one
      stopSpeaking();
    },
  });
}

/** Stop speech imperatively. */
export { stopSpeaking } from '../services/voiceService';
export { isSpeaking } from '../services/voiceService';
