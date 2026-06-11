"use client";

import { Component, type ReactNode } from "react";
import { PixelFrame } from "@/components/pixel-ui";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <PixelFrame>
          <div style={{ padding: "20px 16px", textAlign: "center" }}>
            <p style={{ fontFamily: '"Pixelify Sans", sans-serif', fontSize: 18, color: "var(--pix-red)", marginBottom: 8 }}>
              ⚠️ Something went wrong
            </p>
            <p className="pix-mono" style={{ fontSize: 13, color: "var(--pix-ink-soft)", marginBottom: 12 }}>
              Please refresh the page. If the problem persists, check the browser console for details.
            </p>
            {this.state.error && (
              <pre
                className="pix-mono"
                style={{
                  fontSize: 11,
                  color: "var(--pix-ink-soft)",
                  background: "var(--pix-parch-2)",
                  padding: 8,
                  textAlign: "left",
                  overflow: "auto",
                  maxHeight: 200,
                  border: "2px solid var(--pix-parch-line)",
                }}
              >
                {this.state.error.message}
                {"\n"}
                {this.state.error.stack}
              </pre>
            )}
            <button
              type="button"
              className="pix-btn pix-gold"
              style={{ marginTop: 12 }}
              onClick={() => window.location.reload()}
            >
              🔄 Refresh Page
            </button>
          </div>
        </PixelFrame>
      );
    }
    return this.props.children;
  }
}
