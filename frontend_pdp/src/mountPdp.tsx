import React from "react";
import { createRoot } from "react-dom/client";
import type { PdpBootstrap } from "./types";
import "./tailwind.css";

interface ErrorBoundaryState {
  error: Error | null;
}

class PdpErrorBoundary extends React.Component<
  { children: React.ReactNode },
  ErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-4xl px-4 py-12">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <p className="font-semibold">Custom PDP render error</p>
            <p className="mt-1">{this.state.error.message}</p>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export function mountPdp(
  PdpComponent: React.ComponentType<{ bootstrap: PdpBootstrap }>
) {
  const rootEl = document.getElementById("custom-react-pdp-root");
  if (!rootEl) return;

  let bootstrap = {} as PdpBootstrap;
  try {
    bootstrap = JSON.parse(rootEl.dataset.bootstrap || "{}") as PdpBootstrap;
  } catch (err) {
    console.error("Failed parsing custom PDP bootstrap JSON:", err);
  }

  createRoot(rootEl).render(
    <React.StrictMode>
      <PdpErrorBoundary>
        <PdpComponent bootstrap={bootstrap} />
      </PdpErrorBoundary>
    </React.StrictMode>
  );
}
