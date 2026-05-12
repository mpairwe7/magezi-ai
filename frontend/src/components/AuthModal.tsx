"use client";

import React, { memo, useCallback, useEffect, useState } from 'react';
import { useAuthStore } from '../store/useAuthStore';
import { SparklesIcon } from './Icons';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8802';

interface AuthModalProps {
  open: boolean;
  onClose: () => void;
  defaultMode?: 'signup' | 'login';
}

function AuthModalInner({ open, onClose, defaultMode = 'signup' }: AuthModalProps) {
  const setAuth = useAuthStore((s) => s.setAuth);
  const [mode, setMode] = useState<'login' | 'signup'>(defaultMode);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setMode(defaultMode);
    setError('');
  }, [defaultMode, open]);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const endpoint = mode === 'signup' ? '/v1/auth/signup' : '/v1/auth/login';
      const body = mode === 'signup'
        ? { email, password, name }
        : { email, password };

      const res = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Something went wrong.');
        return;
      }

      setAuth(data.token, data.user);
      onClose();
    } catch {
      setError('Could not connect to server.');
    } finally {
      setLoading(false);
    }
  }, [mode, email, password, name, setAuth, onClose]);

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Sign in to Magezi">
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>

        {mode === 'signup' ? (
          <>
            <h2 className="modal-title">Create your Magezi account</h2>
            <p className="modal-subtitle">
              Keep studying anonymously if you want. An account only adds sync, credits, and settings across devices.
            </p>
            <div className="signup-perks">
              <div className="perk"><SparklesIcon /> <span>50 free tutoring credits</span></div>
              <div className="perk"><SparklesIcon /> <span>Sync your chats across browsers and devices</span></div>
              <div className="perk"><SparklesIcon /> <span>Bring your own API key for unlimited use</span></div>
            </div>
          </>
        ) : (
          <>
            <h2 className="modal-title">Welcome back</h2>
            <p className="modal-subtitle">Sign in to restore your synced Magezi conversations.</p>
          </>
        )}

        <form onSubmit={handleSubmit} className="modal-form">
          {mode === 'signup' && (
            <input
              type="text"
              className="modal-input"
              placeholder="Your name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          )}
          <input
            type="email"
            className="modal-input"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            autoFocus
          />
          <input
            type="password"
            className="modal-input"
            placeholder={mode === 'signup' ? 'Create a password (min 6 chars)' : 'Password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
          />

          {error && <p className="modal-error" role="alert">{error}</p>}

          <button type="submit" className="button modal-submit" disabled={loading}>
            {loading
              ? 'Please wait...'
              : mode === 'signup'
                ? 'Create free account'
                : 'Sign in'}
          </button>
        </form>

        {/* Always show "continue without account" */}
        <button className="modal-skip" onClick={onClose}>
          Continue without an account
        </button>

        <p className="modal-switch">
          {mode === 'signup' ? (
            <>Already have an account?{' '}
              <button className="modal-link" onClick={() => { setMode('login'); setError(''); }}>Sign in</button>
            </>
          ) : (
            <>New here?{' '}
              <button className="modal-link" onClick={() => { setMode('signup'); setError(''); }}>Create free account</button>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

const AuthModal = memo(AuthModalInner);
export default AuthModal;
