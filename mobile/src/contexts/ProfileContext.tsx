import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { supabase } from '../lib/supabase';
import { useSession } from './SessionContext';

type ProfileContextValue = {
  // null = still checking; false = signed in, no user_profiles row yet (onboarding not done,
  // MP-024 next phase); true = onboarding complete. This is the state RootNavigator (MP-022)
  // switches the Onboarding vs. main tab stack on.
  hasCompletedOnboarding: boolean | null;
  refresh: () => Promise<void>;
};

const ProfileContext = createContext<ProfileContextValue | undefined>(undefined);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const { session } = useSession();
  const [hasCompletedOnboarding, setHasCompletedOnboarding] = useState<boolean | null>(null);

  const fetchOnboardingStatus = useCallback(async (): Promise<boolean | null> => {
    if (!session) {
      return null;
    }
    // RLS (MP-013) scopes this to the signed-in user's own row regardless of what id is passed —
    // the .eq() here is belt-and-suspenders for readability, not the security boundary itself.
    const { data, error } = await supabase
      .from('user_profiles')
      .select('id')
      .eq('id', session.user.id)
      .maybeSingle();

    return error ? null : data !== null;
  }, [session]);

  useEffect(() => {
    let ignore = false;
    fetchOnboardingStatus().then((result) => {
      if (!ignore) {
        setHasCompletedOnboarding(result);
      }
    });
    return () => {
      ignore = true;
    };
  }, [fetchOnboardingStatus]);

  const refresh = useCallback(async () => {
    setHasCompletedOnboarding(await fetchOnboardingStatus());
  }, [fetchOnboardingStatus]);

  const value = useMemo<ProfileContextValue>(
    () => ({ hasCompletedOnboarding, refresh }),
    [hasCompletedOnboarding, refresh],
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile(): ProfileContextValue {
  const context = useContext(ProfileContext);
  if (!context) {
    throw new Error('useProfile must be used within a ProfileProvider');
  }
  return context;
}
