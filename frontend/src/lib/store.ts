"use client";

import { useSyncExternalStore } from "react";

// Minimal cross-component signals (breadcrumb title, list refresh) without a
// state library — two values and a change notifier are the entire need.
type Listener = () => void;

function createStore<T>(initial: T) {
  let value = initial;
  const listeners = new Set<Listener>();
  return {
    get: () => value,
    set: (next: T) => {
      value = next;
      for (const l of listeners) l();
    },
    subscribe: (l: Listener) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
}

const breadcrumb = createStore<string>("");
const refreshTick = createStore<number>(0);

export function setBreadcrumb(title: string): void {
  breadcrumb.set(title);
}

export function useBreadcrumb(): string {
  return useSyncExternalStore(breadcrumb.subscribe, breadcrumb.get, () => "");
}

/** Bump after any mutation that changes the meetings list. */
export function bumpRefresh(): void {
  refreshTick.set(refreshTick.get() + 1);
}

export function useRefreshTick(): number {
  return useSyncExternalStore(refreshTick.subscribe, refreshTick.get, () => 0);
}
