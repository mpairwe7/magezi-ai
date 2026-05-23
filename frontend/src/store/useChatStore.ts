import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export interface Citation {
  ref: string;
  source: string;
  page?: string;
  section?: string;
  subject?: string;
  topic?: string;
  year?: string;
  paper?: string;
  passage?: string;
}

const noopStorage: Storage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
  clear: () => {},
  key: () => null,
  length: 0,
};

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  citations?: Citation[];
  faithfulnessScore?: number | null;
  retrievalMode?: string;
  subject?: string;
  groundingWarning?: boolean;
  escalationRequired?: boolean;
  escalationReason?: string;
}

export type SpeechState = 'idle' | 'listening' | 'unavailable' | 'error';
export type Subject = 'physics' | 'chemistry' | 'biology' | 'mathematics' | null;
export type WorkspaceMode = 'anonymous' | 'account';
export type ConversationStatus = 'idle' | 'preparing' | 'streaming' | 'failed';

export interface Conversation {
  id: string;
  title: string;
  subject: Subject;
  locale: string;
  draft: string;
  turns: ChatTurn[];
  sessionId: string;
  createdAt: number;
  updatedAt: number;
  storage: WorkspaceMode;
  synced: boolean;
  hasLoadedTurns: boolean;
  preview: string;
  status: ConversationStatus;
  lastError: string;
}

interface ChatStore {
  workspace: WorkspaceMode;
  userId: string | null;
  conversationsByWorkspace: Record<WorkspaceMode, Record<string, Conversation>>;
  orderByWorkspace: Record<WorkspaceMode, string[]>;
  activeConversationIdByWorkspace: Record<WorkspaceMode, string | null>;
  speechState: SpeechState;
  preferredLocale: string;
  autoNarrate: boolean;
  setWorkspace: (userId: string | null) => void;
  clearAccountWorkspace: () => void;
  setSpeechState: (state: SpeechState) => void;
  setPreferredLocale: (locale: string) => void;
  setAutoNarrate: (on: boolean) => void;
  createConversation: (workspace?: WorkspaceMode, seed?: Partial<Conversation>) => string;
  upsertConversations: (workspace: WorkspaceMode, conversations: Conversation[]) => void;
  hydrateConversation: (workspace: WorkspaceMode, conversation: Conversation) => void;
  setActiveConversation: (id: string, workspace?: WorkspaceMode) => void;
  setDraft: (id: string, value: string, workspace?: WorkspaceMode) => void;
  setConversationLocale: (id: string, locale: string, workspace?: WorkspaceMode) => void;
  setConversationSubject: (id: string, subject: Subject, workspace?: WorkspaceMode) => void;
  setConversationStatus: (
    id: string,
    status: ConversationStatus,
    error?: string,
    workspace?: WorkspaceMode,
  ) => void;
  addTurns: (id: string, turns: ChatTurn[], workspace?: WorkspaceMode) => void;
  replaceTurns: (id: string, turns: ChatTurn[], workspace?: WorkspaceMode) => void;
  updateLastTurn: (
    id: string,
    updater: (turn: ChatTurn) => ChatTurn,
    workspace?: WorkspaceMode,
  ) => void;
  deleteConversation: (id: string, workspace?: WorkspaceMode) => string | null;
  syncConversation: (id: string, workspace?: WorkspaceMode) => void;
  updateConversationMeta: (
    id: string,
    meta: Partial<Pick<Conversation, 'title' | 'preview' | 'sessionId' | 'updatedAt' | 'synced' | 'hasLoadedTurns'>>,
    workspace?: WorkspaceMode,
  ) => void;
}

function generateId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function generateSessionId(): string {
  return `session-${generateId()}`;
}

/* ── CoT stripping ─────────────────────────────────────────────── */

const THINKING_SIGNALS = [
  /^(okay|alright|hmm|well|right|sure|let me|now,)/i,
  /^the user (is |want|ask)/i,
  /^i (need|should|also|will|can|have) /i,
  /^(looking at|checking|passage |but it|but the|it (also|doesn|mention))/i,
  /passage \[?\d/i,
  /^so,? (the|i |none|based|from)/i,
  /^since (the|none|it|this|there)/i,
  /^(therefore|however|also|additionally),? (note|the|i )/i,
  /^(the (main|key|relevant) point|the answer|my response|i.ll |let.s )/i,
  /^(this|that) (means|is|doesn|seem|suggest|passage)/i,
  /not (list|mention|provide|explain|specify|include)/i,
];

function looksLikeThinking(block: string): boolean {
  const trimmed = block.trimStart();
  if (!trimmed) return true;
  return THINKING_SIGNALS.some((rx) => rx.test(trimmed));
}

export function cleanResponse(text: string): string {
  let cleaned = text.trim();
  if (!cleaned) return cleaned;

  const blocks = cleaned.split('\n\n').filter((b) => b.trim());
  if (blocks.length < 2) return cleaned;

  if (!looksLikeThinking(blocks[0])) return cleaned;

  const tags = blocks.map((b) => looksLikeThinking(b));

  let lastAnswerEnd = blocks.length - 1;
  while (lastAnswerEnd >= 0 && tags[lastAnswerEnd]) lastAnswerEnd--;

  if (lastAnswerEnd < 0) return cleaned;

  let lastAnswerStart = lastAnswerEnd;
  for (let i = lastAnswerEnd - 1; i >= 0; i--) {
    if (!tags[i]) lastAnswerStart = i;
    else break;
  }

  cleaned = blocks
    .slice(lastAnswerStart)
    .filter((_, i) => !tags[lastAnswerStart + i])
    .join('\n\n')
    .trim();

  cleaned = cleaned.replace(/\n---\n\*Note/g, '\n\n---\n\n*Note');
  cleaned = cleaned.replace(/([.!?])\s*\*Note:/g, '$1\n\n---\n\n*Note:');

  return cleaned || text.trim();
}

/* ── Helpers ───────────────────────────────────────────────────── */

function normalisePreview(content: string): string {
  const preview = content.replace(/\s+/g, ' ').trim();
  if (preview.length <= 140) return preview;
  return `${preview.slice(0, 137).trimEnd()}...`;
}

function deriveTitleFromTurns(turns: ChatTurn[]): string {
  const firstUserTurn = turns.find((turn) => turn.role === 'user' && turn.content.trim());
  if (!firstUserTurn) return 'New chat';
  const text = firstUserTurn.content.replace(/\s+/g, ' ').trim();
  if (text.length <= 56) return text;
  return `${text.slice(0, 53).trimEnd()}...`;
}

export function createTurn(
  role: 'user' | 'assistant',
  content: string,
  meta?: {
    citations?: Citation[];
    faithfulnessScore?: number | null;
    retrievalMode?: string;
    subject?: string;
    groundingWarning?: boolean;
    escalationRequired?: boolean;
    escalationReason?: string;
  },
): ChatTurn {
  return {
    id: generateId(),
    role,
    content,
    timestamp: Date.now(),
    ...meta,
  };
}

function createConversationRecord(
  storage: WorkspaceMode,
  preferredLocale: string,
  seed: Partial<Conversation> = {},
): Conversation {
  const now = Date.now();
  const turns = seed.turns ?? [];
  const title = seed.title?.trim() || deriveTitleFromTurns(turns) || 'New chat';
  return {
    id: seed.id ?? generateId(),
    title,
    subject: seed.subject ?? null,
    locale: seed.locale ?? preferredLocale,
    draft: seed.draft ?? '',
    turns,
    sessionId: seed.sessionId ?? generateSessionId(),
    createdAt: seed.createdAt ?? now,
    updatedAt: seed.updatedAt ?? now,
    storage,
    synced: seed.synced ?? (storage === 'anonymous'),
    hasLoadedTurns: seed.hasLoadedTurns ?? true,
    preview: seed.preview ?? normalisePreview(turns[turns.length - 1]?.content ?? ''),
    status: seed.status ?? 'idle',
    lastError: seed.lastError ?? '',
  };
}

function withConversation(
  state: ChatStore,
  workspace: WorkspaceMode,
  id: string,
  updater: (conversation: Conversation) => Conversation,
): Pick<ChatStore, 'conversationsByWorkspace' | 'orderByWorkspace' | 'activeConversationIdByWorkspace'> {
  const currentConversation = state.conversationsByWorkspace[workspace][id];
  if (!currentConversation) {
    return {
      conversationsByWorkspace: state.conversationsByWorkspace,
      orderByWorkspace: state.orderByWorkspace,
      activeConversationIdByWorkspace: state.activeConversationIdByWorkspace,
    };
  }

  return {
    conversationsByWorkspace: {
      ...state.conversationsByWorkspace,
      [workspace]: {
        ...state.conversationsByWorkspace[workspace],
        [id]: updater(currentConversation),
      },
    },
    orderByWorkspace: state.orderByWorkspace,
    activeConversationIdByWorkspace: state.activeConversationIdByWorkspace,
  };
}

function ensureWorkspaceConversation(state: ChatStore, workspace: WorkspaceMode): Conversation {
  const activeId = state.activeConversationIdByWorkspace[workspace];
  const existing = activeId ? state.conversationsByWorkspace[workspace][activeId] : null;
  if (existing) return existing;
  return createConversationRecord(workspace, state.preferredLocale);
}

const initialAnonymousConversation = createConversationRecord('anonymous', 'en');

export function selectActiveConversation(state: ChatStore): Conversation | null {
  const workspace = state.workspace;
  const activeId = state.activeConversationIdByWorkspace[workspace];
  if (!activeId) return null;
  return state.conversationsByWorkspace[workspace][activeId] ?? null;
}

export function selectConversationList(state: ChatStore): Conversation[] {
  const workspace = state.workspace;
  return state.orderByWorkspace[workspace]
    .map((id) => state.conversationsByWorkspace[workspace][id])
    .filter(Boolean);
}

const MAX_CHAT_TURNS = 200;
export const initialGreeting: ChatTurn = {
  id: 'greeting-0',
  role: 'assistant',
  content:
    "Oli otya! I'm Magezi, your A-Level STEM tutor. I can help you with Physics, Chemistry, Biology, and Mathematics, all aligned to the NCDC 2025 curriculum. Ask in English, Luganda, Swahili, or Runyankole!",
  timestamp: 0,
};

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      workspace: 'anonymous',
      userId: null,
      conversationsByWorkspace: {
        anonymous: { [initialAnonymousConversation.id]: initialAnonymousConversation },
        account: {},
      },
      orderByWorkspace: {
        anonymous: [initialAnonymousConversation.id],
        account: [],
      },
      activeConversationIdByWorkspace: {
        anonymous: initialAnonymousConversation.id,
        account: null,
      },
      speechState: 'idle',
      preferredLocale: 'en',
      autoNarrate: false,
      setWorkspace: (userId) =>
        set((state) => {
          const workspace: WorkspaceMode = userId ? 'account' : 'anonymous';
          const workspaceUnchanged = state.workspace === workspace && state.userId === userId;

          if (!userId) {
            const accountEmpty = state.orderByWorkspace.account.length === 0
              && state.activeConversationIdByWorkspace.account === null
              && Object.keys(state.conversationsByWorkspace.account).length === 0;
            if (workspaceUnchanged && accountEmpty) {
              return state;
            }
            return {
              workspace,
              userId,
              conversationsByWorkspace: {
                ...state.conversationsByWorkspace,
                account: {},
              },
              orderByWorkspace: {
                ...state.orderByWorkspace,
                account: [],
              },
              activeConversationIdByWorkspace: {
                ...state.activeConversationIdByWorkspace,
                account: null,
              },
            } as Partial<ChatStore> as ChatStore;
          }

          const hasAccountConversation = state.orderByWorkspace.account.length > 0
            && state.activeConversationIdByWorkspace.account
            && state.conversationsByWorkspace.account[state.activeConversationIdByWorkspace.account];
          if (hasAccountConversation) {
            if (workspaceUnchanged) return state;
            return { workspace, userId } as Partial<ChatStore> as ChatStore;
          }
          const nextState: Partial<ChatStore> = { workspace, userId };

          const created = createConversationRecord('account', state.preferredLocale, {
            synced: false,
            hasLoadedTurns: true,
          });
          nextState.conversationsByWorkspace = {
            ...state.conversationsByWorkspace,
            account: { [created.id]: created },
          };
          nextState.orderByWorkspace = {
            ...state.orderByWorkspace,
            account: [created.id],
          };
          nextState.activeConversationIdByWorkspace = {
            ...state.activeConversationIdByWorkspace,
            account: created.id,
          };
          return nextState as ChatStore;
        }),
      clearAccountWorkspace: () =>
        set((state) => {
          const accountEmpty = state.orderByWorkspace.account.length === 0
            && state.activeConversationIdByWorkspace.account === null
            && Object.keys(state.conversationsByWorkspace.account).length === 0;
          if (accountEmpty) return state;
          return {
            conversationsByWorkspace: {
              ...state.conversationsByWorkspace,
              account: {},
            },
            orderByWorkspace: {
              ...state.orderByWorkspace,
              account: [],
            },
            activeConversationIdByWorkspace: {
              ...state.activeConversationIdByWorkspace,
              account: null,
            },
          };
        }),
      setSpeechState: (state) => set({ speechState: state }),
      setPreferredLocale: (locale) => set({ preferredLocale: locale }),
      setAutoNarrate: (on) => set({ autoNarrate: on }),
      createConversation: (workspace = get().workspace, seed = {}) => {
        const created = createConversationRecord(workspace, get().preferredLocale, seed);
        set((state) => ({
          conversationsByWorkspace: {
            ...state.conversationsByWorkspace,
            [workspace]: {
              ...state.conversationsByWorkspace[workspace],
              [created.id]: created,
            },
          },
          orderByWorkspace: {
            ...state.orderByWorkspace,
            [workspace]: [created.id, ...state.orderByWorkspace[workspace].filter((id) => id !== created.id)],
          },
          activeConversationIdByWorkspace: {
            ...state.activeConversationIdByWorkspace,
            [workspace]: created.id,
          },
        }));
        return created.id;
      },
      upsertConversations: (workspace, conversations) =>
        set((state) => {
          const currentMap = state.conversationsByWorkspace[workspace];
          const nextMap = { ...currentMap };

          for (const incoming of conversations) {
            const existing = currentMap[incoming.id];
            nextMap[incoming.id] = {
              ...(existing ?? createConversationRecord(workspace, state.preferredLocale, incoming)),
              ...incoming,
              storage: workspace,
              draft: existing?.draft ?? incoming.draft ?? '',
              turns: incoming.hasLoadedTurns
                ? incoming.turns
                : (existing?.turns ?? []),
              hasLoadedTurns: incoming.hasLoadedTurns ?? existing?.hasLoadedTurns ?? false,
              status: existing?.status ?? incoming.status ?? 'idle',
              lastError: existing?.lastError ?? incoming.lastError ?? '',
            };
          }

          const incomingOrder = conversations.map((conversation) => conversation.id);
          const nextOrder = [
            ...incomingOrder,
            ...state.orderByWorkspace[workspace].filter((id) => !incomingOrder.includes(id)),
          ].filter((id, index, array) => array.indexOf(id) === index && nextMap[id]);

          const nextActive = state.activeConversationIdByWorkspace[workspace]
            && nextMap[state.activeConversationIdByWorkspace[workspace]!]
            ? state.activeConversationIdByWorkspace[workspace]
            : (nextOrder[0] ?? null);

          return {
            conversationsByWorkspace: {
              ...state.conversationsByWorkspace,
              [workspace]: nextMap,
            },
            orderByWorkspace: {
              ...state.orderByWorkspace,
              [workspace]: nextOrder,
            },
            activeConversationIdByWorkspace: {
              ...state.activeConversationIdByWorkspace,
              [workspace]: nextActive,
            },
          };
        }),
      hydrateConversation: (workspace, conversation) =>
        set((state) => ({
          conversationsByWorkspace: {
            ...state.conversationsByWorkspace,
            [workspace]: {
              ...state.conversationsByWorkspace[workspace],
              [conversation.id]: conversation,
            },
          },
          orderByWorkspace: {
            ...state.orderByWorkspace,
            [workspace]: [conversation.id, ...state.orderByWorkspace[workspace].filter((id) => id !== conversation.id)],
          },
        })),
      setActiveConversation: (id, workspace = get().workspace) =>
        set((state) => {
          const currentActive = state.activeConversationIdByWorkspace[workspace];
          const currentOrder = state.orderByWorkspace[workspace];
          if (currentActive === id && currentOrder[0] === id) {
            return state;
          }
          return {
            activeConversationIdByWorkspace: {
              ...state.activeConversationIdByWorkspace,
              [workspace]: id,
            },
            orderByWorkspace: {
              ...state.orderByWorkspace,
              [workspace]: currentOrder[0] === id
                ? currentOrder
                : [id, ...currentOrder.filter((conversationId) => conversationId !== id)],
            },
          };
        }),
      setDraft: (id, value, workspace = get().workspace) =>
        set((state) => withConversation(state, workspace, id, (conversation) => ({
          ...conversation,
          draft: value,
        }))),
      setConversationLocale: (id, locale, workspace = get().workspace) =>
        set((state) => {
          const updated = withConversation(state, workspace, id, (conversation) => ({
            ...conversation,
            locale,
            updatedAt: Date.now(),
          }));
          return {
            ...updated,
            preferredLocale: locale,
          };
        }),
      setConversationSubject: (id, subject, workspace = get().workspace) =>
        set((state) => withConversation(state, workspace, id, (conversation) => ({
          ...conversation,
          subject,
          updatedAt: Date.now(),
        }))),
      setConversationStatus: (id, status, error = '', workspace = get().workspace) =>
        set((state) => withConversation(state, workspace, id, (conversation) => {
          if (conversation.status === status && conversation.lastError === error) {
            return conversation;
          }
          return { ...conversation, status, lastError: error };
        })),
      addTurns: (id, turns, workspace = get().workspace) =>
        set((state) => withConversation(state, workspace, id, (conversation) => {
          const nextTurns = [...conversation.turns, ...turns].slice(-MAX_CHAT_TURNS);
          const title = conversation.title === 'New chat'
            ? deriveTitleFromTurns(nextTurns)
            : conversation.title;
          return {
            ...conversation,
            turns: nextTurns,
            title,
            preview: normalisePreview(nextTurns[nextTurns.length - 1]?.content ?? conversation.preview),
            updatedAt: Date.now(),
            lastError: '',
          };
        })),
      replaceTurns: (id, turns, workspace = get().workspace) =>
        set((state) => withConversation(state, workspace, id, (conversation) => ({
          ...conversation,
          turns: turns.slice(-MAX_CHAT_TURNS),
          title: conversation.title === 'New chat' ? deriveTitleFromTurns(turns) : conversation.title,
          preview: normalisePreview(turns[turns.length - 1]?.content ?? ''),
          updatedAt: Date.now(),
          hasLoadedTurns: true,
        }))),
      updateLastTurn: (id, updater, workspace = get().workspace) =>
        set((state) => withConversation(state, workspace, id, (conversation) => {
          if (conversation.turns.length === 0) return conversation;
          const nextTurns = [...conversation.turns];
          nextTurns[nextTurns.length - 1] = updater(nextTurns[nextTurns.length - 1]);
          return {
            ...conversation,
            turns: nextTurns,
            preview: normalisePreview(nextTurns[nextTurns.length - 1]?.content ?? conversation.preview),
            updatedAt: Date.now(),
          };
        })),
      deleteConversation: (id, workspace = get().workspace) => {
        let nextActiveId: string | null = null;
        set((state) => {
          const nextMap = { ...state.conversationsByWorkspace[workspace] };
          delete nextMap[id];
          let nextOrder = state.orderByWorkspace[workspace].filter((conversationId) => conversationId !== id);

          if (nextOrder.length === 0) {
            const created = createConversationRecord(workspace, state.preferredLocale, {
              synced: workspace === 'anonymous',
              hasLoadedTurns: true,
            });
            nextMap[created.id] = created;
            nextOrder = [created.id];
            nextActiveId = created.id;
          } else {
            nextActiveId = state.activeConversationIdByWorkspace[workspace] === id
              ? nextOrder[0]
              : (state.activeConversationIdByWorkspace[workspace] ?? nextOrder[0]);
          }

          return {
            conversationsByWorkspace: {
              ...state.conversationsByWorkspace,
              [workspace]: nextMap,
            },
            orderByWorkspace: {
              ...state.orderByWorkspace,
              [workspace]: nextOrder,
            },
            activeConversationIdByWorkspace: {
              ...state.activeConversationIdByWorkspace,
              [workspace]: nextActiveId,
            },
          };
        });
        return nextActiveId;
      },
      syncConversation: (id, workspace = get().workspace) =>
        set((state) => withConversation(state, workspace, id, (conversation) => ({
          ...conversation,
          synced: true,
          hasLoadedTurns: true,
        }))),
      updateConversationMeta: (id, meta, workspace = get().workspace) =>
        set((state) => withConversation(state, workspace, id, (conversation) => ({
          ...conversation,
          ...meta,
        }))),
    }),
    {
      name: 'magezi-chat-store',
      storage: createJSONStorage(() => {
        if (typeof window === 'undefined') return noopStorage;
        return localStorage;
      }),
      partialize: (state) => ({
        conversationsByWorkspace: {
          anonymous: state.conversationsByWorkspace.anonymous,
          account: {},
        },
        orderByWorkspace: {
          anonymous: state.orderByWorkspace.anonymous,
          account: [],
        },
        activeConversationIdByWorkspace: {
          anonymous: state.activeConversationIdByWorkspace.anonymous,
          account: null,
        },
        preferredLocale: state.preferredLocale,
        autoNarrate: state.autoNarrate,
      }),
    },
  ),
);

// Make sure a usable anonymous conversation always exists after hydration.
const state = useChatStore.getState();
if (!selectActiveConversation(state)) {
  useChatStore.getState().createConversation('anonymous');
}

export function getActiveConversationHistory(conversation: Conversation): { role: 'user' | 'assistant'; content: string }[] {
  return conversation.turns
    .filter((turn) => turn.content.trim())
    .slice(-10)
    .map((turn) => ({ role: turn.role, content: turn.content }));
}

export function getDisplayTurns(conversation: Conversation | null): ChatTurn[] {
  if (!conversation || conversation.turns.length > 0) return conversation?.turns ?? [];
  return [initialGreeting];
}

export function ensureActiveConversation(workspace: WorkspaceMode = useChatStore.getState().workspace): Conversation {
  const currentState = useChatStore.getState();
  const activeConversation = selectActiveConversation(currentState);
  if (activeConversation && activeConversation.storage === workspace) return activeConversation;

  const fallback = ensureWorkspaceConversation(currentState, workspace);
  if (!currentState.conversationsByWorkspace[workspace][fallback.id]) {
    useChatStore.getState().createConversation(workspace, fallback);
  }
  return fallback;
}
