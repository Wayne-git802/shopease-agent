import React, { Component } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

class ErrorBoundary extends Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: '100vh',
          display: 'grid',
          placeItems: 'center',
          padding: 24,
          fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
          background: '#f5f7fb',
          color: '#172033'
        }}>
          <div style={{
            maxWidth: 480,
            padding: 32,
            border: '1px solid #dbe3ef',
            borderRadius: 12,
            background: 'white',
            boxShadow: '0 18px 50px rgba(37,52,89,0.12)',
            textAlign: 'center'
          }}>
            <h2 style={{ margin: '0 0 10px', fontSize: 22 }}>Something went wrong</h2>
            <p style={{ color: '#64748b', margin: '0 0 20px', lineHeight: 1.6 }}>
              The page crashed due to an unexpected error. This is usually caused by corrupted data. Reload the page to reset.
            </p>
            <pre style={{
              padding: '12px 16px',
              borderRadius: 8,
              background: '#fef2f2',
              color: '#b91c1c',
              fontSize: 13,
              textAlign: 'left',
              overflow: 'auto',
              maxHeight: 120,
              margin: '0 0 20px'
            }}>
              {this.state.error.message}
            </pre>
            <button
              onClick={() => {
                Object.keys(localStorage).forEach((key) => {
                  if (key.startsWith('shopease_')) localStorage.removeItem(key);
                });
                window.location.reload();
              }}
              style={{
                minHeight: 40,
                padding: '0 20px',
                border: '1px solid #0f766e',
                borderRadius: 8,
                background: '#0f766e',
                color: 'white',
                fontWeight: 700,
                cursor: 'pointer',
                fontSize: 15
              }}
            >
              Reset data and reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
