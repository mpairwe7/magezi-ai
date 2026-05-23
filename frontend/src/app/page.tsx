"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from 'react';
import AuthModal from '../components/AuthModal';
import ChatInput from '../components/ChatInput';
import ChatMessage from '../components/ChatMessage';
import ConversationRail from '../components/ConversationRail';
import SettingsPanel from '../components/SettingsPanel';
import SubjectSelector from '../components/SubjectSelector';
import {
  BookIcon,
  BotIcon,
  LoadingDots,
  MenuIcon,
  PlusIcon,
  SpeakerIcon,
  TrashIcon,
  UserIcon,
} from '../components/Icons';
import {
  deleteConversation as deleteRemoteConversation,
  fetchConversationDetail,
  fetchConversations,
  fetchProfile,
  RemoteConversationDetail,
  RemoteConversationSummary,
  useHealth,
  useSubjects,
} from '../hooks/useApi';
import { useOnlineStatus } from '../hooks/useOnlineStatus';
import { useTtsAvailable } from '../hooks/useSpeech';
import { FOLLOW_UP_PROMPTS, GENERAL_STARTER_PROMPTS, getSubjectPrompts } from '../lib/subjects';
import { speak, stopSpeaking } from '../services/voiceService';
import { useShallow } from 'zustand/react/shallow';
import { useAuthStore } from '../store/useAuthStore';
import {
  ChatTurn,
  cleanResponse,
  Conversation,
  createTurn,
  getDisplayTurns,
  selectActiveConversation,
  selectConversationList,
  Subject,
  useChatStore,
  WorkspaceMode,
} from '../store/useChatStore';

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onerror: ((e: Event) => void) | null;
  onend: (() => void) | null;
  onresult: ((e: SpeechRecognitionEvent) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface SpeechRecognitionEvent extends Event {
  results: {
    [i: number]: { 0: { transcript: string }; isFinal: boolean; length: number };
    length: number;
  };
}

interface PendingRequest {
  conversationId: string;
  workspace: WorkspaceMode;
  controller: AbortController;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8802';

const LOCALE_OPTIONS = [
  { value: 'en', label: 'EN' },
  { value: 'lg', label: 'LG' },
  { value: 'sw', label: 'SW' },
  { value: 'nyn', label: 'NY' },
] as const;

const LOCALE_SPEECH: Record<string, string> = {
  en: 'en-US',
  lg: 'lg-UG',
  sw: 'sw-KE',
  nyn: 'nyn-UG',
};

function mapRemoteSummary(summary: RemoteConversationSummary): Conversation {
  return {
    id: summary.id,
    title: summary.title || 'New chat',
    subject: (summary.subject as Subject | null) ?? null,
    locale: summary.locale,
    draft: '',
    turns: [],
    sessionId: summary.session_id,
    createdAt: summary.created_at * 1000,
    updatedAt: summary.updated_at * 1000,
    storage: 'account',
    synced: true,
    hasLoadedTurns: false,
    preview: summary.preview,
    status: 'idle',
    lastError: '',
  };
}

function mapRemoteDetail(detail: RemoteConversationDetail): Conversation {
  return {
    ...mapRemoteSummary(detail.conversation),
    turns: detail.messages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      timestamp: message.timestamp * 1000,
      citations: (message.citations as ChatTurn['citations']) ?? [],
      faithfulnessScore: message.faithfulness_score ?? null,
      retrievalMode: message.retrieval_mode,
      subject: message.subject ?? undefined,
      groundingWarning: message.grounding_warning ?? false,
      escalationRequired: message.escalation_required ?? false,
      escalationReason: message.escalation_reason ?? '',
    })),
    hasLoadedTurns: true,
  };
}

function buildHistoryPayload(conversation: Conversation, message: string, skipUserTurn: boolean) {
  const turns = conversation.turns.filter((turn) => turn.content.trim());
  const baseTurns = (
    skipUserTurn
    && turns[turns.length - 1]?.role === 'user'
    && turns[turns.length - 1]?.content.trim() === message.trim()
  )
    ? turns.slice(0, -1)
    : turns;

  return baseTurns.slice(-10).map((turn) => ({
    role: turn.role,
    content: turn.content,
  }));
}

export default function Page() {
  const workspace = useChatStore((state) => state.workspace);
  const activeConversation = useChatStore(selectActiveConversation);
  const conversations = useChatStore(useShallow(selectConversationList));
  const speechState = useChatStore((state) => state.speechState);
  const preferredLocale = useChatStore((state) => state.preferredLocale);
  const autoNarrate = useChatStore((state) => state.autoNarrate);
  const setWorkspace = useChatStore((state) => state.setWorkspace);
  const clearAccountWorkspace = useChatStore((state) => state.clearAccountWorkspace);
  const setSpeechState = useChatStore((state) => state.setSpeechState);
  const setAutoNarrate = useChatStore((state) => state.setAutoNarrate);
  const createConversation = useChatStore((state) => state.createConversation);
  const upsertConversations = useChatStore((state) => state.upsertConversations);
  const hydrateConversation = useChatStore((state) => state.hydrateConversation);
  const setActiveConversation = useChatStore((state) => state.setActiveConversation);
  const setDraft = useChatStore((state) => state.setDraft);
  const setConversationLocale = useChatStore((state) => state.setConversationLocale);
  const setConversationSubject = useChatStore((state) => state.setConversationSubject);
  const setConversationStatus = useChatStore((state) => state.setConversationStatus);
  const addTurns = useChatStore((state) => state.addTurns);
  const replaceTurns = useChatStore((state) => state.replaceTurns);
  const updateLastTurn = useChatStore((state) => state.updateLastTurn);
  const deleteConversationStore = useChatStore((state) => state.deleteConversation);
  const syncConversation = useChatStore((state) => state.syncConversation);

  const authToken = useAuthStore((state) => state.token);
  const authUser = useAuthStore((state) => state.user);
  const updateCredits = useAuthStore((state) => state.updateCredits);
  const updateUser = useAuthStore((state) => state.updateUser);

  const isOnline = useOnlineStatus();
  const ttsAvailable = useTtsAvailable();
  const { data: health } = useHealth();
  const { data: subjects } = useSubjects();

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const requestRef = useRef<PendingRequest | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatAreaRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const [showAuth, setShowAuth] = useState(false);
  const [showAuthMode, setShowAuthMode] = useState<'signup' | 'login'>('signup');
  const [showSettings, setShowSettings] = useState(false);
  const [showRail, setShowRail] = useState(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [nudgeDismissed, setNudgeDismissed] = useState(false);
  const [, startTransition] = useTransition();

  const displayTurns = useMemo(() => getDisplayTurns(activeConversation), [activeConversation]);
  const locale = activeConversation?.locale ?? preferredLocale;
  const subject = activeConversation?.subject ?? null;
  const draft = activeConversation?.draft ?? '';
  const isStreaming = activeConversation?.status === 'preparing' || activeConversation?.status === 'streaming';
  const hasStarted = (activeConversation?.turns.length ?? 0) > 0;
  const userMessageCount = activeConversation?.turns.filter((turn) => turn.role === 'user').length ?? 0;
  const latestAssistantTurnId = useMemo(() => {
    for (let index = displayTurns.length - 1; index >= 0; index -= 1) {
      if (displayTurns[index].role === 'assistant' && displayTurns[index].id !== 'greeting-0') {
        return displayTurns[index].id;
      }
    }
    return null;
  }, [displayTurns]);

  useEffect(() => {
    setWorkspace(authUser?.id ?? null);
  }, [authUser?.id, setWorkspace]);

  const authUserId = authUser?.id ?? null;

  useEffect(() => {
    if (!authToken || !authUserId) {
      clearAccountWorkspace();
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const profile = await fetchProfile(authToken);
        if (!cancelled && profile.user) {
          updateUser(profile.user);
        }
      } catch {
        // Keep the persisted auth snapshot until the user explicitly signs out.
      }

      try {
        const remoteConversations = await fetchConversations(authToken);
        if (cancelled) return;
        upsertConversations(
          'account',
          remoteConversations.map((conversation) => mapRemoteSummary(conversation)),
        );
      } catch {
        if (!cancelled && activeConversation?.storage === 'account') {
          setConversationStatus(activeConversation.id, 'failed', 'Could not load synced conversations.', 'account');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // Dep is authUserId (primitive), not authUser (object) — updateUser() in
    // the body would otherwise create a new authUser ref every run and loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authToken, authUserId, clearAccountWorkspace, updateUser, upsertConversations]);

  const activeConversationId = activeConversation?.id ?? null;
  const activeConversationSynced = activeConversation?.synced ?? false;
  const activeConversationLoaded = activeConversation?.hasLoadedTurns ?? false;

  useEffect(() => {
    if (
      workspace !== 'account'
      || !authToken
      || !activeConversationId
      || !activeConversationSynced
      || activeConversationLoaded
    ) {
      return;
    }

    let cancelled = false;
    setConversationStatus(activeConversationId, 'preparing', '', 'account');

    fetchConversationDetail(authToken, activeConversationId)
      .then((detail) => {
        if (cancelled) return;
        hydrateConversation('account', mapRemoteDetail(detail));
      })
      .catch(() => {
        if (!cancelled) {
          setConversationStatus(activeConversationId, 'failed', 'Could not load this conversation.', 'account');
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeConversationId, activeConversationSynced, activeConversationLoaded, authToken, hydrateConversation, setConversationStatus, workspace]);

  useEffect(() => {
    const element = chatAreaRef.current;
    if (!element) {
      setShowScrollBtn(false);
      return;
    }

    const onScroll = () => {
      const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
      shouldAutoScrollRef.current = distanceFromBottom < 120;
      setShowScrollBtn(distanceFromBottom > 220);
    };

    onScroll();
    element.addEventListener('scroll', onScroll, { passive: true });
    return () => element.removeEventListener('scroll', onScroll);
  }, [hasStarted]);

  const lastRenderKey = `${activeConversation?.id ?? 'none'}:${displayTurns[displayTurns.length - 1]?.id ?? 'empty'}:${displayTurns[displayTurns.length - 1]?.content.length ?? 0}`;
  useEffect(() => {
    if (!shouldAutoScrollRef.current) return;
    messagesEndRef.current?.scrollIntoView({ behavior: hasStarted ? 'smooth' : 'auto' });
  }, [hasStarted, lastRenderKey]);

  useEffect(() => {
    if (recognitionRef.current) {
      recognitionRef.current.abort();
      recognitionRef.current = null;
    }
    const browserWindow = typeof window !== 'undefined'
      ? window as Window & {
        SpeechRecognition?: new () => SpeechRecognition;
        webkitSpeechRecognition?: new () => SpeechRecognition;
      }
      : null;
    const Recognition = browserWindow && (browserWindow.SpeechRecognition || browserWindow.webkitSpeechRecognition);
    if (!Recognition) {
      setSpeechState('unavailable');
      return;
    }

    const recognition = new Recognition();
    recognition.lang = LOCALE_SPEECH[locale] ?? 'en-US';
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onstart = () => setSpeechState('listening');
    recognition.onerror = () => setSpeechState('error');
    recognition.onend = () => setSpeechState('idle');
    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results?.[0]?.[0]?.transcript;
      if (transcript && activeConversation) {
        setDraft(activeConversation.id, transcript, workspace);
      }
    };
    recognitionRef.current = recognition;
    return () => recognition.abort();
  }, [activeConversation, locale, setDraft, setSpeechState, workspace]);

  const healthOk = isOnline && health?.status === 'ok' && health?.llm === 'ready';
  const healthLabel = useMemo(() => {
    if (!isOnline) return 'Offline';
    if (!health) return 'Connecting...';
    return healthOk ? 'NCDC 2025' : health.status === 'ok' ? 'Starting...' : 'Unavailable';
  }, [health, healthOk, isOnline]);

  const quickPrompts = useMemo(() => (
    hasStarted
      ? FOLLOW_UP_PROMPTS
      : (subject ? getSubjectPrompts(subject, subjects) : GENERAL_STARTER_PROMPTS)
  ), [hasStarted, subject, subjects]);

  const scrollToBottom = useCallback(() => {
    shouldAutoScrollRef.current = true;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const stopActiveRequest = useCallback(() => {
    const pending = requestRef.current;
    if (!pending) return;
    pending.controller.abort();
    requestRef.current = null;
  }, []);

  const handleSelectConversation = useCallback((conversationId: string) => {
    if (requestRef.current && requestRef.current.conversationId !== conversationId) {
      stopActiveRequest();
    }
    shouldAutoScrollRef.current = true;
    setActiveConversation(conversationId, workspace);
    setShowRail(false);
    requestAnimationFrame(() => composerRef.current?.focus());
  }, [setActiveConversation, stopActiveRequest, workspace]);

  const handleNewConversation = useCallback(() => {
    stopActiveRequest();
    shouldAutoScrollRef.current = true;
    const nextId = createConversation(workspace, {
      locale,
      subject: null,
      synced: workspace === 'anonymous',
      hasLoadedTurns: true,
    });
    setShowRail(false);
    requestAnimationFrame(() => {
      setActiveConversation(nextId, workspace);
      composerRef.current?.focus();
    });
  }, [createConversation, locale, setActiveConversation, stopActiveRequest, workspace]);

  const handleDeleteConversation = useCallback(async (conversationId: string) => {
    const conversation = conversations.find((item) => item.id === conversationId);
    if (!conversation) return;

    if (requestRef.current?.conversationId === conversationId) {
      stopActiveRequest();
    }

    const nextActive = deleteConversationStore(conversationId, workspace);
    if (workspace === 'account' && authToken && conversation.synced) {
      try {
        await deleteRemoteConversation(authToken, conversationId);
      } catch {
        const remoteConversations = await fetchConversations(authToken);
        upsertConversations('account', remoteConversations.map((item) => mapRemoteSummary(item)));
      }
    }

  }, [authToken, conversations, deleteConversationStore, stopActiveRequest, upsertConversations, workspace]);

  const sendMessage = useCallback(async (textOverride?: string, options?: { skipUserTurn?: boolean }) => {
    const currentState = useChatStore.getState();
    const conversation = selectActiveConversation(currentState);
    const currentWorkspace = currentState.workspace;
    if (!conversation) return;

    const text = (textOverride ?? conversation.draft).trim();
    if (!text || requestRef.current) return;

    if (!isOnline) {
      addTurns(conversation.id, [createTurn('assistant', 'You are offline. Reconnect to keep chatting.')], currentWorkspace);
      return;
    }

    const skipUserTurn = options?.skipUserTurn ?? false;
    const controller = new AbortController();
    requestRef.current = {
      conversationId: conversation.id,
      workspace: currentWorkspace,
      controller,
    };

    setConversationStatus(conversation.id, 'preparing', '', currentWorkspace);
    const history = buildHistoryPayload(conversation, text, skipUserTurn);

    if (!skipUserTurn) {
      addTurns(conversation.id, [createTurn('user', text, { subject: conversation.subject ?? undefined })], currentWorkspace);
    }
    setDraft(conversation.id, '', currentWorkspace);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Session-ID': conversation.sessionId,
    };
    if (authToken && currentWorkspace === 'account') {
      headers.Authorization = `Bearer ${authToken}`;
    }

    const payload = {
      message: text,
      top_k: 4,
      locale: conversation.locale,
      subject: conversation.subject,
      session_id: conversation.sessionId,
      conversation_id: currentWorkspace === 'account' ? conversation.id : undefined,
      history,
    };

    try {
      const response = await fetch(`${API_URL}/v1/chat/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        if (response.status === 402) {
          addTurns(conversation.id, [createTurn('assistant', 'No credits left. Add your API key or keep chatting anonymously on this device.')], currentWorkspace);
          setConversationStatus(conversation.id, 'idle', '', currentWorkspace);
          requestRef.current = null;
          return;
        }

        const syncResponse = await fetch(`${API_URL}/v1/chat`, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
          signal: controller.signal,
        });
        if (!syncResponse.ok) throw new Error(`API ${syncResponse.status}`);
        const data = await syncResponse.json();
        if (data.credits_remaining != null) updateCredits(data.credits_remaining);
        if (data.subject) {
          setConversationSubject(conversation.id, data.subject as Subject, currentWorkspace);
        }
        if (currentWorkspace === 'account') syncConversation(conversation.id, currentWorkspace);
        addTurns(conversation.id, [createTurn('assistant', cleanResponse(data.reply), {
          citations: data.citations ?? [],
          faithfulnessScore: data.faithfulness_score ?? null,
          retrievalMode: data.retrieval_mode ?? 'keyword',
          subject: data.subject ?? conversation.subject ?? undefined,
          groundingWarning: data.grounding_warning ?? false,
          escalationRequired: data.escalation_required ?? false,
          escalationReason: data.escalation_reason ?? '',
        })], currentWorkspace);
        setConversationStatus(conversation.id, 'idle', '', currentWorkspace);
        if (autoNarrate && ttsAvailable && data.reply) {
          speak(data.reply, conversation.locale).catch(() => {});
        }
        requestRef.current = null;
        return;
      }

      const assistantTurn = createTurn('assistant', '', { subject: conversation.subject ?? undefined });
      addTurns(conversation.id, [assistantTurn], currentWorkspace);
      setConversationStatus(conversation.id, 'streaming', '', currentWorkspace);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let eventName = 'token';
      let streamed = '';
      let pendingMeta: {
        citations?: ChatTurn['citations'];
        faithfulnessScore?: number | null;
        retrievalMode?: string;
        subject?: string;
        groundingWarning?: boolean;
      } = {};

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventName = line.slice(7).trim();
              continue;
            }
            if (!line.startsWith('data: ')) continue;
            const data = line.slice(6);
            if (eventName === 'metadata') {
              try {
                const meta = JSON.parse(data);
                pendingMeta = {
                  ...pendingMeta,
                  citations: meta.citations ?? pendingMeta.citations,
                  retrievalMode: meta.retrieval_mode ?? pendingMeta.retrievalMode,
                  subject: meta.subject ?? pendingMeta.subject,
                };
                if (meta.subject) {
                  setConversationSubject(conversation.id, meta.subject as Subject, currentWorkspace);
                }
                if (meta.credits_remaining != null) {
                  updateCredits(meta.credits_remaining);
                }
                if (currentWorkspace === 'account') {
                  syncConversation(conversation.id, currentWorkspace);
                }
              } catch {
                // Ignore malformed metadata chunks.
              }
              eventName = 'token';
              continue;
            }
            if (eventName === 'grounding') {
              try {
                const meta = JSON.parse(data);
                pendingMeta = {
                  ...pendingMeta,
                  faithfulnessScore: meta.faithfulness_score ?? pendingMeta.faithfulnessScore ?? null,
                  groundingWarning: meta.grounding_warning ?? pendingMeta.groundingWarning ?? false,
                };
              } catch {
                // Ignore malformed grounding chunks.
              }
              eventName = 'token';
              continue;
            }
            if (eventName === 'error') {
              updateLastTurn(conversation.id, (turn) => ({
                ...turn,
                content: data || 'An error occurred.',
              }), currentWorkspace);
              setConversationStatus(conversation.id, 'failed', data || 'An error occurred.', currentWorkspace);
              eventName = 'token';
              continue;
            }
            if (eventName === 'done') {
              eventName = 'token';
              continue;
            }

            streamed += data;
            updateLastTurn(conversation.id, (turn) => ({
              ...turn,
              content: streamed,
              citations: pendingMeta.citations ?? turn.citations,
              faithfulnessScore: pendingMeta.faithfulnessScore ?? turn.faithfulnessScore,
              retrievalMode: pendingMeta.retrievalMode ?? turn.retrievalMode,
              subject: pendingMeta.subject ?? turn.subject,
              groundingWarning: pendingMeta.groundingWarning ?? turn.groundingWarning,
            }), currentWorkspace);
            eventName = 'token';
          }
        }
      } finally {
        reader.releaseLock();
      }

      streamed = cleanResponse(streamed);
      updateLastTurn(conversation.id, (turn) => ({
        ...turn,
        content: streamed,
      }), currentWorkspace);
      if (currentWorkspace === 'account') syncConversation(conversation.id, currentWorkspace);
      setConversationStatus(conversation.id, 'idle', '', currentWorkspace);
      if (autoNarrate && ttsAvailable && streamed) {
        speak(streamed, conversation.locale).catch(() => {});
      }
    } catch {
      if (controller.signal.aborted) {
        const currentConversation = useChatStore.getState().conversationsByWorkspace[currentWorkspace][conversation.id];
        const lastTurn = currentConversation?.turns[currentConversation.turns.length - 1];
        if (lastTurn?.role === 'assistant' && !lastTurn.content.trim()) {
          updateLastTurn(conversation.id, (turn) => ({ ...turn, content: 'Response stopped.' }), currentWorkspace);
        }
        setConversationStatus(conversation.id, 'idle', '', currentWorkspace);
      } else {
        const currentConversation = useChatStore.getState().conversationsByWorkspace[currentWorkspace][conversation.id];
        const lastTurn = currentConversation?.turns[currentConversation.turns.length - 1];
        if (lastTurn?.role === 'assistant' && !lastTurn.content.trim()) {
          updateLastTurn(conversation.id, (turn) => ({ ...turn, content: 'Could not connect. Please try again.' }), currentWorkspace);
        } else {
          addTurns(conversation.id, [createTurn('assistant', 'Could not connect. Please try again.')], currentWorkspace);
        }
        setConversationStatus(conversation.id, 'failed', 'Could not connect. Please try again.', currentWorkspace);
      }
    } finally {
      if (requestRef.current?.conversationId === conversation.id) {
        requestRef.current = null;
      }
      composerRef.current?.focus();
    }
  }, [addTurns, authToken, autoNarrate, isOnline, setConversationStatus, setConversationSubject, setDraft, syncConversation, ttsAvailable, updateCredits, updateLastTurn]);

  const handleRetryLatest = useCallback((turnId: string) => {
    const currentConversation = selectActiveConversation(useChatStore.getState());
    if (!currentConversation) return;

    const assistantIndex = currentConversation.turns.findIndex((turn) => turn.id === turnId);
    if (assistantIndex === -1) return;
    const isLatestAssistant = currentConversation.turns.findLast((turn) => turn.role === 'assistant')?.id === turnId;
    if (!isLatestAssistant) return;

    const previousUser = currentConversation.turns
      .slice(0, assistantIndex)
      .reverse()
      .find((turn) => turn.role === 'user');
    if (!previousUser) return;

    replaceTurns(currentConversation.id, currentConversation.turns.slice(0, assistantIndex), workspace);
    void sendMessage(previousUser.content, { skipUserTurn: true });
  }, [replaceTurns, sendMessage, workspace]);

  const handleMicClick = useCallback(() => {
    if (!recognitionRef.current) return;
    if (speechState === 'listening') {
      recognitionRef.current.stop();
      return;
    }
    recognitionRef.current.start();
  }, [speechState]);

  const handleCancelRecording = useCallback(() => {
    if (recognitionRef.current && speechState === 'listening') {
      recognitionRef.current.abort();
    }
  }, [speechState]);

  const handleLocaleChange = useCallback((nextLocale: string) => {
    if (!activeConversation) return;
    startTransition(() => {
      setConversationLocale(activeConversation.id, nextLocale, workspace);
    });
  }, [activeConversation, setConversationLocale, workspace]);

  const handleSubjectChange = useCallback((nextSubject: Subject) => {
    if (!activeConversation) return;
    startTransition(() => {
      setConversationSubject(activeConversation.id, nextSubject, workspace);
    });
  }, [activeConversation, setConversationSubject, workspace]);

  const handleQuickPrompt = useCallback((prompt: string) => {
    const nextPrompt = hasStarted ? prompt : `Explain ${prompt}`;
    void sendMessage(nextPrompt);
  }, [hasStarted, sendMessage]);

  return (
    <main id="main-content" className="app-shell app-shell-threads">
      <ConversationRail
        open={showRail}
        conversations={conversations}
        activeConversationId={activeConversation?.id ?? null}
        workspace={workspace}
        authUser={authUser}
        subjects={subjects}
        onClose={() => setShowRail(false)}
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onOpenAuth={() => { setShowAuthMode('signup'); setShowAuth(true); }}
        onOpenSettings={() => setShowSettings(true)}
      />

      <section className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            <button className="rail-toggle" onClick={() => setShowRail(true)} aria-label="Open conversations">
              <MenuIcon />
            </button>
            <h1 className="topbar-brand">Magezi</h1>
            <span className={`topbar-health ${healthOk ? 'pill-ok' : 'pill-warn'}`}>
              {healthLabel}
            </span>
          </div>
          <div className="topbar-right">
            <div className="locale-switch" role="radiogroup" aria-label="Response language">
              {LOCALE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  role="radio"
                  aria-checked={locale === option.value}
                  onClick={() => handleLocaleChange(option.value)}
                  className="locale-btn"
                >
                  {option.label}
                </button>
              ))}
            </div>
            {ttsAvailable && (
              <button
                className="narrate-toggle"
                aria-pressed={autoNarrate}
                onClick={() => {
                  setAutoNarrate(!autoNarrate);
                  if (autoNarrate) stopSpeaking();
                }}
                title={autoNarrate ? 'Auto-narrate on' : 'Auto-narrate off'}
              >
                <SpeakerIcon /> {autoNarrate ? 'ON' : 'OFF'}
              </button>
            )}
            <button className="topbar-action" onClick={handleNewConversation} aria-label="Start a new chat" title="New chat">
              <PlusIcon />
            </button>
            {hasStarted && activeConversation && (
              <button
                className="topbar-action topbar-action-danger"
                onClick={() => handleDeleteConversation(activeConversation.id)}
                aria-label="Delete this conversation"
                title="Delete chat"
              >
                <TrashIcon />
              </button>
            )}
            {authUser ? (
              <button className="user-btn" onClick={() => setShowSettings(true)}>
                <UserIcon />
                <span className="user-btn-credits">
                  {authUser.has_api_key ? '\u221e' : authUser.credits}
                </span>
              </button>
            ) : (
              <button className="user-btn" onClick={() => { setShowAuthMode('signup'); setShowAuth(true); }}>
                <UserIcon /> Sync
              </button>
            )}
          </div>
        </header>

        {!isOnline && (
          <div className="offline-banner" role="alert">
            You are offline. Existing threads stay readable, but new questions wait for reconnection.
          </div>
        )}

        {!hasStarted ? (
          <div className="welcome-screen">
            <div className="welcome-center">
              <div className="welcome-badge"><BookIcon /> A-Level STEM Tutor</div>
              <h2 className="welcome-title">What would you like to learn?</h2>
              <p className="welcome-sub">
                Magezi teaches A-Level STEM step by step, grounded in the NCDC 2025 curriculum.
              </p>
              <SubjectSelector selected={subject} onSelect={handleSubjectChange} subjects={subjects} />
              <div className="welcome-prompts-grid">
                {quickPrompts.slice(0, 4).map((prompt) => (
                  <button key={prompt} className="welcome-prompt-card" onClick={() => handleQuickPrompt(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
            <div className="welcome-composer">
              <ChatInput
                ref={composerRef}
                message={draft}
                isStreaming={isStreaming}
                speechUnavailable={speechState === 'unavailable'}
                speechState={speechState}
                locale={locale}
                onMessageChange={(value) => activeConversation && setDraft(activeConversation.id, value, workspace)}
                onSend={sendMessage}
                isRecording={speechState === 'listening'}
                onMicClick={handleMicClick}
                onCancelRecording={handleCancelRecording}
                onStop={stopActiveRequest}
              />
            </div>
          </div>
        ) : (
          <>
            <section className="thread-header">
              <div>
                <p className="thread-kicker">{workspace === 'anonymous' ? 'Anonymous thread' : 'Synced thread'}</p>
                <h2 className="thread-title">{activeConversation?.title ?? 'New chat'}</h2>
                <p className="thread-subtitle">
                  {workspace === 'anonymous'
                    ? 'Stored locally on this device'
                    : 'Saved to your Magezi account'}
                </p>
              </div>
              <SubjectSelector selected={subject} onSelect={handleSubjectChange} subjects={subjects} />
            </section>

            <div ref={chatAreaRef} className="chat-area" role="log" aria-live="polite" aria-busy={isStreaming}>
              {displayTurns.map((turn) => (
                <ChatMessage
                  key={turn.id}
                  turn={turn}
                  locale={locale}
                  subjects={subjects}
                  canRetry={turn.id === latestAssistantTurnId}
                  onRetry={handleRetryLatest}
                />
              ))}
              {isStreaming && (() => {
                const lastTurn = activeConversation?.turns[activeConversation.turns.length - 1];
                if (lastTurn?.role === 'assistant' && lastTurn.content) return null;
                return (
                  <article className="message-row" aria-label="Magezi is thinking">
                    <div className="avatar assistant" aria-hidden="true"><BotIcon /></div>
                    <div className="bubble assistant">
                      <span className="bubble-role">magezi</span>
                      {activeConversation?.status === 'preparing'
                        ? <span className="thinking-indicator">Preparing context...</span>
                        : <LoadingDots />}
                    </div>
                  </article>
                );
              })()}
              <div ref={messagesEndRef} />
            </div>

            {showScrollBtn && (
              <button className="scroll-bottom-btn" onClick={scrollToBottom} aria-label="Scroll to latest message">
                &darr;
              </button>
            )}

            {!isStreaming && (
              <div className="quick-prompts">
                {quickPrompts.map((prompt) => (
                  <button key={prompt} className="quick-chip" onClick={() => handleQuickPrompt(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
            )}

            {!authUser && !nudgeDismissed && userMessageCount >= 5 && (
              <div className="nudge-banner">
                <span>Anonymous mode is active. Sign in only if you want sync and 50 starter credits.</span>
                <button className="nudge-btn" onClick={() => { setShowAuthMode('signup'); setShowAuth(true); }}>
                  Sign in to sync
                </button>
                <button className="nudge-dismiss" onClick={() => setNudgeDismissed(true)} aria-label="Dismiss">
                  &times;
                </button>
              </div>
            )}

            <div className="composer-dock">
              <ChatInput
                ref={composerRef}
                message={draft}
                isStreaming={isStreaming}
                speechUnavailable={speechState === 'unavailable'}
                speechState={speechState}
                locale={locale}
                onMessageChange={(value) => activeConversation && setDraft(activeConversation.id, value, workspace)}
                onSend={sendMessage}
                isRecording={speechState === 'listening'}
                onMicClick={handleMicClick}
                onCancelRecording={handleCancelRecording}
                onStop={stopActiveRequest}
              />
            </div>
          </>
        )}
      </section>

      <AuthModal open={showAuth} onClose={() => setShowAuth(false)} defaultMode={showAuthMode} />
      <SettingsPanel open={showSettings} onClose={() => setShowSettings(false)} />
    </main>
  );
}
