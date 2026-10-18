"use client";

import { Component, type ReactNode } from "react";

/** Keeps one panel's failure (for example an unexpected API shape) from taking down the whole report. */
export default class SafeBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
