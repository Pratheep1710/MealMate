import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { supabase } from './supabase';

// MP-068: Expo push token registration. Docs pulled from
// https://docs.expo.dev/versions/v57.0.0/sdk/notifications/ per mobile/AGENTS.md's "Expo has
// changed" warning — SDK 57 requires an explicit `projectId` for getExpoPushTokenAsync and an
// Android notification channel created before the token request, both handled below.
//
// Every failure mode here (no physical device, permission denied, no EAS project configured yet —
// see the projectId note) is a silent no-op, not a thrown error: registration is a background
// nicety on app launch, and a user who never gets a push token should still get a working app.

// getExpoPushTokenAsync falls back to Constants.expoConfig.extra.eas.projectId automatically, but
// this repo has no eas.json/EAS project linked yet (flagged in docs/MP-068-070-push-notifications.md)
// — reading it explicitly here, rather than omitting the option, makes that gap visible in one
// place instead of failing inside the SDK with a less legible error.
function getProjectId(): string | undefined {
  return Constants.expoConfig?.extra?.eas?.projectId as string | undefined;
}

async function ensureAndroidChannel(): Promise<void> {
  if (Platform.OS !== 'android') {
    return;
  }
  await Notifications.setNotificationChannelAsync('default', {
    name: 'default',
    importance: Notifications.AndroidImportance.MAX,
  });
}

/** Returns the device's Expo push token, or null if registration isn't possible right now
 * (simulator, permission denied, no project id, offline). Never throws. */
export async function registerForPushNotificationsAsync(): Promise<string | null> {
  if (!Device.isDevice) {
    // Simulators/emulators can't receive real push notifications — Expo's own guidance.
    return null;
  }

  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== 'granted') {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== 'granted') {
    return null;
  }

  const projectId = getProjectId();
  if (!projectId) {
    return null;
  }

  try {
    await ensureAndroidChannel();
    const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
    return data;
  } catch {
    // Network failure, misconfigured project, etc. — registration retries next app launch.
    return null;
  }
}

/** Registers the token for the signed-in user via the register_push_token RPC
 * (0013_push_tokens_schema.sql) rather than a direct table insert/update — that migration's
 * comment explains why a direct RLS-scoped client write can't reassign a device's token across
 * users (the usual device-handoff case) the way plan_items' direct-write edits can. The RPC
 * hardcodes the caller's own auth.uid() server-side, so there's no user id for the client to pass
 * or get wrong.
 */
export async function syncPushToken(token: string): Promise<void> {
  await supabase.rpc('register_push_token', { token });
}

/** Unregisters this device's push token so a signed-out device stops receiving the outgoing
 * user's reminders (0014_push_token_unregister.sql) — must be called while the session is still
 * active (auth.uid() needs it) and therefore before supabase.auth.signOut(), not after. Same
 * silent-no-op philosophy as registration: sign-out must never be blocked or fail because push
 * cleanup didn't work.
 */
export async function unregisterPushToken(): Promise<void> {
  if (!Device.isDevice) {
    return;
  }
  const projectId = getProjectId();
  if (!projectId) {
    return;
  }
  try {
    const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId });
    await supabase.rpc('unregister_push_token', { token });
  } catch {
    // Permission revoked, offline, RPC failure — nothing actionable to do differently on sign-out.
  }
}
