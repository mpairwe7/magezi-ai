import React from 'react';

export default function Loading() {
  return (
    <main style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '60vh', gap: '1rem',
    }}>
      <div aria-busy="true" aria-label="Loading Magezi" style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem',
      }}>
        <div style={{
          width: 48, height: 48, borderRadius: '50%',
          border: '3px solid var(--border-1)',
          borderTopColor: 'var(--accent-green)',
          animation: 'spin 0.8s linear infinite',
        }} />
        <p style={{ color: 'var(--text-2)', fontSize: '0.9rem' }}>
          Loading Magezi...
        </p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </main>
  );
}
