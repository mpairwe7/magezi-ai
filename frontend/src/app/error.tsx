"use client";

import React from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main role="alert" style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', minHeight: '60vh', gap: '1rem',
      padding: '2rem', textAlign: 'center',
    }}>
      <h2 style={{ fontSize: '1.5rem', color: 'var(--text-0)' }}>
        Something went wrong
      </h2>
      <p style={{ color: 'var(--text-2)', maxWidth: '40ch' }}>
        {error.message || 'An unexpected error occurred. Please try again.'}
      </p>
      <button
        onClick={reset}
        className="button"
        style={{ marginTop: '0.5rem' }}
      >
        Try again
      </button>
    </main>
  );
}
