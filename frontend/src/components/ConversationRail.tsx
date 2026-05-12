import React, { memo, useMemo, useState } from 'react';
import type { SubjectInfo } from '../hooks/useApi';
import { getSubjectInfo } from '../lib/subjects';
import { Conversation, WorkspaceMode } from '../store/useChatStore';
import { UserProfile } from '../store/useAuthStore';
import { CloseIcon, MessageSquareIcon, PlusIcon, TrashIcon, UserIcon } from './Icons';

interface ConversationRailProps {
  open: boolean;
  conversations: Conversation[];
  activeConversationId: string | null;
  workspace: WorkspaceMode;
  authUser: UserProfile | null;
  subjects?: SubjectInfo[];
  onClose: () => void;
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onOpenAuth: () => void;
  onOpenSettings: () => void;
}

function formatTimestamp(timestamp: number) {
  const diff = Date.now() - timestamp;
  if (diff < 60_000) return 'now';
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m`;
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h`;
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(timestamp);
}

type TimeGroup = 'Today' | 'Yesterday' | 'Previous 7 days' | 'Previous 30 days' | 'Older';

function getTimeGroup(timestamp: number): TimeGroup {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86_400_000);
  const week = new Date(today.getTime() - 7 * 86_400_000);
  const month = new Date(today.getTime() - 30 * 86_400_000);

  if (timestamp >= today.getTime()) return 'Today';
  if (timestamp >= yesterday.getTime()) return 'Yesterday';
  if (timestamp >= week.getTime()) return 'Previous 7 days';
  if (timestamp >= month.getTime()) return 'Previous 30 days';
  return 'Older';
}

function groupConversations(convs: Conversation[]): [TimeGroup, Conversation[]][] {
  const groups = new Map<TimeGroup, Conversation[]>();
  const order: TimeGroup[] = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Older'];

  for (const c of convs) {
    const g = getTimeGroup(c.updatedAt);
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g)!.push(c);
  }

  return order.filter((g) => groups.has(g)).map((g) => [g, groups.get(g)!]);
}

function ConversationRailInner({
  open,
  conversations,
  activeConversationId,
  workspace,
  authUser,
  subjects,
  onClose,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
  onOpenAuth,
  onOpenSettings,
}: ConversationRailProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const q = searchQuery.toLowerCase();
    return conversations.filter((c) =>
      c.title.toLowerCase().includes(q)
      || (c.preview ?? '').toLowerCase().includes(q),
    );
  }, [conversations, searchQuery]);

  const grouped = useMemo(() => groupConversations(filtered), [filtered]);

  return (
    <>
      <div
        className={`rail-overlay ${open ? 'rail-overlay-open' : ''}`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside className={`conversation-rail ${open ? 'conversation-rail-open' : ''}`}>
        <div className="rail-top">
          <div>
            <p className="rail-eyebrow">Workspace</p>
            <h2 className="rail-title">{workspace === 'anonymous' ? 'Anonymous' : 'Your chats'}</h2>
          </div>
          <button className="rail-close" onClick={onClose} aria-label="Close conversation rail">
            <CloseIcon />
          </button>
        </div>

        <button className="rail-new" onClick={onNewConversation}>
          <PlusIcon /> New chat
        </button>

        <div className="rail-search-wrap">
          <input
            className="rail-search"
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search conversations"
          />
        </div>

        <div className="rail-account-card">
          {authUser ? (
            <button className="rail-account-button" onClick={onOpenSettings}>
              <span className="rail-account-avatar"><UserIcon /></span>
              <span>
                <strong>{authUser.name || authUser.email}</strong>
                <small>{authUser.has_api_key ? 'Unlimited mode' : `${authUser.credits} credits left`}</small>
              </span>
            </button>
          ) : (
            <>
              <p className="rail-account-copy">
                Anonymous mode keeps chats on this device. Sign in only if you want cross-device sync.
              </p>
              <button className="button" onClick={onOpenAuth}>Sign in to sync</button>
            </>
          )}
        </div>

        <div className="rail-list" role="list" aria-label="Conversation threads">
          {grouped.map(([group, items]) => (
            <div key={group} className="rail-group">
              <div className="rail-group-label">{group}</div>
              {items.map((conversation) => {
                const subjectInfo = getSubjectInfo(conversation.subject, subjects);
                const isActive = conversation.id === activeConversationId;
                const preview = conversation.preview || (conversation.turns[0]?.content ?? 'Start a new conversation');
                return (
                  <div
                    key={conversation.id}
                    className={`rail-item ${isActive ? 'rail-item-active' : ''}`}
                    role="listitem"
                  >
                    <button
                      className="rail-item-main"
                      onClick={() => onSelectConversation(conversation.id)}
                    >
                      <span className="rail-item-head">
                        <span className="rail-item-title">{conversation.title}</span>
                        <span className="rail-item-time">{formatTimestamp(conversation.updatedAt)}</span>
                      </span>
                      <span className="rail-item-preview">{preview}</span>
                      <span className="rail-item-meta">
                        {subjectInfo && (
                          <span className="rail-item-subject" style={{ color: subjectInfo.color }}>
                            {subjectInfo.name}
                          </span>
                        )}
                        {conversation.status === 'streaming' && <span className="rail-item-status">live</span>}
                        {!conversation.synced && workspace === 'account' && <span className="rail-item-status">local draft</span>}
                        {workspace === 'anonymous' && <span className="rail-item-status">device only</span>}
                      </span>
                    </button>
                    <button
                      className="rail-item-delete"
                      onClick={() => onDeleteConversation(conversation.id)}
                      aria-label={`Delete ${conversation.title}`}
                      title="Delete conversation"
                    >
                      <TrashIcon />
                    </button>
                  </div>
                );
              })}
            </div>
          ))}
          {conversations.length === 0 && (
            <div className="rail-empty">
              <MessageSquareIcon />
              <span>Your conversations will appear here.</span>
            </div>
          )}
          {searchQuery && filtered.length === 0 && conversations.length > 0 && (
            <div className="rail-empty">
              <span>No matching conversations</span>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

export default memo(ConversationRailInner);
