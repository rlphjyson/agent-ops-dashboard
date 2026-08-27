"use client";

import { useSyncExternalStore } from "react";

const THEME_STORAGE_KEY = "agent_ops_theme";

type Theme = "light" | "dark";
type Listener = () => void;

let theme: Theme = "light";
let initialized = false;
let listeners: Listener[] = [];

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyClass(value: Theme) {
  document.documentElement.classList.toggle("dark", value === "dark");
}

function ensureInitialized() {
  if (initialized) return;
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  theme = stored === "dark" || stored === "light" ? stored : systemPrefersDark() ? "dark" : "light";
  initialized = true;
}

function notify() {
  for (const listener of listeners) listener();
}

/**
 * A minimal external store wrapping localStorage + the <html> "dark" class, same pattern as
 * token-store.ts's useSyncExternalStore-based approach. The initial class is actually applied by
 * an inline, beforeInteractive script in the root layout (see app/layout.tsx) so there's no
 * flash of the wrong theme before hydration -- this store's job is keeping subsequent toggles
 * (and any other component reading the current theme) in sync with that.
 */
export const themeStore = {
  getSnapshot(): Theme {
    ensureInitialized();
    return theme;
  },
  getServerSnapshot(): Theme {
    return "light";
  },
  subscribe(listener: Listener): () => void {
    listeners.push(listener);
    return () => {
      listeners = listeners.filter((l) => l !== listener);
    };
  },
  toggle(): void {
    ensureInitialized();
    theme = theme === "dark" ? "light" : "dark";
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    applyClass(theme);
    notify();
  },
};

export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const currentTheme = useSyncExternalStore(
    themeStore.subscribe,
    themeStore.getSnapshot,
    themeStore.getServerSnapshot,
  );
  return { theme: currentTheme, toggleTheme: themeStore.toggle };
}

/** The literal source of the beforeInteractive script -- kept here, next to the store whose
 * storage key/logic it must stay consistent with, rather than duplicated as an inline string. */
export const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
    var dark = stored === "dark" || (stored !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    if (dark) document.documentElement.classList.add("dark");
  } catch (e) {}
})();
`;
