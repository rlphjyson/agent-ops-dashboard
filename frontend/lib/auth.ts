"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { tokenStore } from "./token-store";

interface Auth {
  token: string | null;
  setToken: (token: string) => void;
  logout: () => void;
}

export function useAuth(): Auth {
  const token = useSyncExternalStore(
    tokenStore.subscribe,
    tokenStore.getSnapshot,
    tokenStore.getServerSnapshot,
  );

  return { token, setToken: tokenStore.setToken, logout: tokenStore.clearToken };
}

/** Redirects to /login if there is no stored token. */
export function useRequireAuth(): Auth {
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    // Read the store directly rather than trusting this render's `auth.token` closure: on the
    // very first effect run after hydration, that value may still be the getServerSnapshot
    // placeholder (null) even though the store itself already has the real value, since React's
    // hydration-mismatch correction lands as a separate, later render rather than synchronously
    // before this effect. tokenStore.getSnapshot() is always current.
    if (!tokenStore.getSnapshot()) router.replace("/login");
  }, [auth.token, router]);

  return auth;
}
