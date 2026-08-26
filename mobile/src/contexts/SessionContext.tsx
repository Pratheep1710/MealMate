import type { Session } from '@supabase/supabase-js';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { unregisterPushToken } from '../lib/pushRegistration';
import { supabase } from '../lib/supabase';
import { clearAllCache } from '../lib/weekCache';

type SessionContextValue = {
  session: Session | null;
  // Distinguishes "still checking SecureStore for a persisted session" from "checked, and
  // there isn't one" — RootNavigator (MP-022) needs this third state to avoid flashing the
  // sign-in screen for a user who's actually already authenticated.
  initializing: boolean;
  signInWithPassword: (email: string, password: string) => Promise<{ error: string | null }>;
  // `needsConfirmation` distinguishes "account created, session started immediately" from "check
  // your email to confirm" — which of those happens depends on the Supabase project's email
  // confirmation setting, not on anything the client controls: a signed-in `data.session` on the
  // response means the project auto-confirms, its absence means a confirmation email was sent.
  signUp: (
    email: string,
    password: string,
  ) => Promise<{ error: string | null; needsConfirmation: boolean }>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | undefined>(undefined);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setInitializing(false);
    });

    // Covers sign-in, sign-out, and token refresh (auto or manual) with one subscription —
    // supabase-js emits TOKEN_REFRESHED here too, so this is also MP-023's "session refresh"
    // handling, not just a login/logout listener.
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
    });

    return () => subscription.unsubscribe();
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      initializing,
      signInWithPassword: async (email: string, password: string) => {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        return { error: error?.message ?? null };
      },
      signUp: async (email: string, password: string) => {
        const { data, error } = await supabase.auth.signUp({ email, password });
        return { error: error?.message ?? null, needsConfirmation: !error && !data.session };
      },
      signOut: async () => {
        // Must run before auth.signOut() — unregisterPushToken needs auth.uid() to still resolve
        // to the outgoing user (see 0014_push_token_unregister.sql).
        await unregisterPushToken();
        await supabase.auth.signOut();
        // Prevents the next sign-in on this device (a different account) from ever reading this
        // account's cached offline data — see weekCache.ts.
        await clearAllCache();
      },
    }),
    [session, initializing],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return context;
}
