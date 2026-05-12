"use client";

import React, { memo, useCallback, useState } from 'react';
import { useAuthStore, UserProfile } from '../store/useAuthStore';
import { SparklesIcon } from './Icons';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8802';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

function SettingsPanelInner({ open, onClose }: SettingsPanelProps) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const updateUser = useAuthStore((s) => s.updateUser);
  const logout = useAuthStore((s) => s.logout);

  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const handleSaveKey = useCallback(async (nextApiKey: string) => {
    if (!token) return;
    setSaving(true);
    setMessage('');
    try {
      const res = await fetch(`${API_URL}/v1/auth/apikey`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ api_key: nextApiKey }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage(data.detail || 'Failed to save key.');
        return;
      }
      updateUser(data.user as UserProfile);
      setApiKey('');
      setMessage(nextApiKey ? 'API key saved. Unlimited mode is active.' : 'API key removed.');
    } catch {
      setMessage('Could not connect to server.');
    } finally {
      setSaving(false);
    }
  }, [token, updateUser]);

  if (!open || !user) return null;

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Settings">
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">Settings</h2>

        <div className="settings-section">
          <h3 className="settings-label">Account</h3>
          <p className="settings-value">{user.email}</p>
          <p className="settings-value">
            Plan: <strong>{user.plan === 'byok' ? 'Bring Your Own Key' : 'Free'}</strong>
          </p>
        </div>

        <div className="settings-section">
          <h3 className="settings-label">Credits remaining</h3>
          <div className="credits-display">
            <span className="credits-number">{user.credits}</span>
            <span className="credits-label">message credits</span>
          </div>
          {user.has_api_key && (
            <p className="settings-note" style={{ color: 'var(--accent-green)' }}>
              <SparklesIcon /> Your own API key is active — unlimited usage
            </p>
          )}
        </div>

        <div className="settings-section">
          <h3 className="settings-label">Bring Your Own Key</h3>
          <p className="settings-note">
            Add your Anthropic API key for unlimited usage. Get one at{' '}
            <a href="https://console.anthropic.com" target="_blank" rel="noopener noreferrer">
              console.anthropic.com
            </a>
          </p>
          <div className="settings-key-row">
            <input
              type="password"
              className="modal-input"
              placeholder="sk-ant-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <button
              className="button"
              onClick={() => handleSaveKey(apiKey)}
              disabled={saving}
              style={{ flexShrink: 0 }}
            >
              {saving ? '...' : 'Save'}
            </button>
          </div>
          {user.has_api_key && (
            <button
              className="button secondary"
              onClick={() => handleSaveKey('')}
              style={{ marginTop: '0.5rem', fontSize: '0.78rem' }}
            >
              Remove my key
            </button>
          )}
          {message && <p className="settings-message">{message}</p>}
        </div>

        <div className="settings-actions">
          <button className="button secondary" onClick={onClose}>Close</button>
          <button className="button secondary" onClick={() => { logout(); onClose(); }}
            style={{ color: 'var(--danger)' }}>
            Sign out to anonymous mode
          </button>
        </div>
      </div>
    </div>
  );
}

const SettingsPanel = memo(SettingsPanelInner);
export default SettingsPanel;
