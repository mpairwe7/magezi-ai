import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8802';

// ---------------------------------------------------------------------------
// Health check — polled every 60s, drives the "NCDC Aligned" badge state
// ---------------------------------------------------------------------------
interface HealthData {
  status: string;
  model: string;
  retriever: string;
  llm: string;
  subjects: string[];
}

export function useHealth() {
  return useQuery<HealthData>({
    queryKey: ['health'],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/health`);
      if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
      return res.json();
    },
    refetchInterval: 60_000,
    retry: 1,
  });
}

// ---------------------------------------------------------------------------
// Subjects — cached, fetched once
// ---------------------------------------------------------------------------
export interface SubjectInfo {
  id: string;
  name: string;
  name_lg: string;
  icon: string;
  color: string;
  starter_prompts: string[];
}

export function useSubjects() {
  return useQuery<SubjectInfo[]>({
    queryKey: ['subjects'],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/v1/subjects`);
      if (!res.ok) throw new Error(`Subjects fetch failed: ${res.status}`);
      const data = await res.json();
      return data.subjects;
    },
    staleTime: Infinity,
  });
}

// ---------------------------------------------------------------------------
// Feedback mutation — optimistic, fire-and-forget
// ---------------------------------------------------------------------------
interface FeedbackPayload {
  message_id: string;
  rating: 'up' | 'down';
  user_query: string;
  bot_reply: string;
}

export function useFeedback() {
  const qc = useQueryClient();
  return useMutation<void, Error, FeedbackPayload>({
    mutationFn: async (payload) => {
      const res = await fetch(`${API_URL}/v1/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Feedback failed: ${res.status}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['health'] });
    },
  });
}

export interface RemoteConversationSummary {
  id: string;
  title: string;
  subject: string | null;
  locale: string;
  session_id: string;
  preview: string;
  message_count: number;
  created_at: number;
  updated_at: number;
}

export interface RemoteConversationMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  citations?: Array<Record<string, string>>;
  faithfulness_score?: number | null;
  retrieval_mode?: string;
  subject?: string | null;
  grounding_warning?: boolean;
  escalation_required?: boolean;
  escalation_reason?: string;
}

export interface RemoteConversationDetail {
  conversation: RemoteConversationSummary;
  messages: RemoteConversationMessage[];
}

export async function fetchProfile(token: string) {
  const res = await fetch(`${API_URL}/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Profile fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchConversations(token: string): Promise<RemoteConversationSummary[]> {
  const res = await fetch(`${API_URL}/v1/conversations`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Conversation list failed: ${res.status}`);
  return res.json();
}

export async function fetchConversationDetail(token: string, conversationId: string): Promise<RemoteConversationDetail> {
  const res = await fetch(`${API_URL}/v1/conversations/${conversationId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Conversation detail failed: ${res.status}`);
  return res.json();
}

export async function deleteConversation(token: string, conversationId: string) {
  const res = await fetch(`${API_URL}/v1/conversations/${conversationId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Conversation delete failed: ${res.status}`);
  return res.json();
}
