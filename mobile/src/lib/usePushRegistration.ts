import { useEffect } from 'react';

import { useSession } from '../contexts/SessionContext';
import { registerForPushNotificationsAsync, syncPushToken } from './pushRegistration';

// MP-068: registers this device's Expo push token once per session, mounted only from
// MainTabNavigator (i.e. only for a signed-in, fully onboarded user — RootNavigator's state
// boundary). Fire-and-forget: registerForPushNotificationsAsync already no-ops on every failure
// mode, so there's nothing actionable to surface to the UI here.
export function usePushRegistration(): void {
  const { session } = useSession();
  const userId = session?.user.id;

  useEffect(() => {
    if (!userId) {
      return;
    }
    let cancelled = false;
    void (async () => {
      const token = await registerForPushNotificationsAsync();
      if (token && !cancelled) {
        await syncPushToken(token);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);
}
