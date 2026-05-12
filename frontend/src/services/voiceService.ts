/**
 * Magezi Voice Service — client-side speech I/O
 *
 * 2026 approach: Use native browser APIs for both input and output.
 * - Input:  Web Speech API (recognition) + MediaRecorder (fallback)
 * - Output: Web Speech Synthesis API (TTS) — works offline, zero backend
 *
 * This avoids heavy server-side ASR/TTS models while delivering
 * a complete voice loop for the hackathon demo.
 */

// ---------------------------------------------------------------------------
// TTS — Web Speech Synthesis API
// ---------------------------------------------------------------------------
const VOICE_LANG_MAP: Record<string, string[]> = {
  en: ['en-US', 'en-GB', 'en'],
  lg: ['lg-UG', 'en-US'],    // Luganda voices rare — fallback to English
  sw: ['sw-KE', 'sw', 'en-US'],
  nyn: ['nyn-UG', 'en-US'],  // Runyankole voices rare — fallback
};

let _selectedVoice: SpeechSynthesisVoice | null = null;
let _currentUtterance: SpeechSynthesisUtterance | null = null;

function _findVoice(locale: string): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !window.speechSynthesis) return null;
  const voices = window.speechSynthesis.getVoices();
  const candidates = VOICE_LANG_MAP[locale] ?? ['en-US'];

  for (const lang of candidates) {
    const match = voices.find(
      (v) => v.lang === lang || v.lang.startsWith(lang.split('-')[0])
    );
    if (match) return match;
  }
  return voices[0] ?? null;
}

/** Ensure voices are loaded (Chrome loads async). */
export function initVoices(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      resolve();
      return;
    }
    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) { resolve(); return; }
    window.speechSynthesis.addEventListener('voiceschanged', () => resolve(), { once: true });
    // Safety timeout — some browsers never fire voiceschanged
    setTimeout(resolve, 2000);
  });
}

/** Check if TTS is available. */
export function isTtsAvailable(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/** Speak text aloud using Web Speech Synthesis. Returns a promise that resolves when done. */
export function speak(text: string, locale: string = 'en'): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!isTtsAvailable()) { reject(new Error('TTS unavailable')); return; }

    // Cancel any ongoing speech
    stopSpeaking();

    const utterance = new SpeechSynthesisUtterance(text);
    _currentUtterance = utterance;

    // Select voice for locale
    const voice = _findVoice(locale);
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang;
    }

    utterance.rate = 0.95;   // Slightly slower for educational content
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    utterance.onend = () => { _currentUtterance = null; resolve(); };
    utterance.onerror = (e) => {
      _currentUtterance = null;
      // 'canceled' is not a real error
      if (e.error === 'canceled' || e.error === 'interrupted') { resolve(); return; }
      reject(e);
    };

    window.speechSynthesis.speak(utterance);
  });
}

/** Stop any ongoing speech. */
export function stopSpeaking(): void {
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  _currentUtterance = null;
}

/** Is speech currently playing? */
export function isSpeaking(): boolean {
  if (typeof window === 'undefined' || !window.speechSynthesis) return false;
  return window.speechSynthesis.speaking;
}


// ---------------------------------------------------------------------------
// Audio Recording — MediaRecorder API (fallback for Web Speech API)
// ---------------------------------------------------------------------------
export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private _isRecording = false;

  static isSupported(): boolean {
    return typeof window !== 'undefined' && 'MediaRecorder' in window && 'mediaDevices' in navigator;
  }

  get isRecording(): boolean { return this._isRecording; }

  async start(): Promise<void> {
    if (this._isRecording) return;

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000,
      },
    });

    this.chunks = [];
    this.mediaRecorder = new MediaRecorder(this.stream, {
      mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm',
    });

    this.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };

    this.mediaRecorder.start(250); // 250ms chunks
    this._isRecording = true;
  }

  async stop(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.mediaRecorder || !this._isRecording) {
        resolve(new Blob([]));
        return;
      }

      this.mediaRecorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: 'audio/webm' });
        this._cleanup();
        resolve(blob);
      };

      this.mediaRecorder.stop();
      this._isRecording = false;
    });
  }

  cancel(): void {
    if (this.mediaRecorder && this._isRecording) {
      this.mediaRecorder.stop();
    }
    this._isRecording = false;
    this._cleanup();
  }

  private _cleanup(): void {
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    this.mediaRecorder = null;
    this.chunks = [];
  }
}
