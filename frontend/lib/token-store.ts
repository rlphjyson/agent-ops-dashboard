const TOKEN_STORAGE_KEY = "docuchat_token";

type Listener = () => void;

let token: string | null = null;
let initialized = false;
let listeners: Listener[] = [];

function ensureInitialized() {
  if (initialized) return;
  token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  initialized = true;
}

function notify() {
  for (const listener of listeners) listener();
}

/**
 * A minimal external store wrapping localStorage, for use with useSyncExternalStore.
 * localStorage's own "storage" event only fires in *other* tabs, so writes made here
 * notify subscribers directly to keep the current tab in sync too.
 */
export const tokenStore = {
  getSnapshot(): string | null {
    ensureInitialized();
    return token;
  },
  getServerSnapshot(): string | null {
    return null;
  },
  subscribe(listener: Listener): () => void {
    listeners.push(listener);
    return () => {
      listeners = listeners.filter((l) => l !== listener);
    };
  },
  setToken(newToken: string) {
    ensureInitialized();
    token = newToken;
    window.localStorage.setItem(TOKEN_STORAGE_KEY, newToken);
    notify();
  },
  clearToken() {
    ensureInitialized();
    token = null;
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    notify();
  },
};
