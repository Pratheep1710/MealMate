import 'react-native-url-polyfill/auto';

import { createClient, type SupportedStorage } from '@supabase/supabase-js';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// MP-023: session tokens must never sit in plaintext storage. expo-secure-store is backed by the
// iOS Keychain / Android Keystore, not AsyncStorage — this adapter is the only place session data
// touches disk on native, so there is exactly one path to audit for that guarantee.
//
// expo-secure-store has no web implementation (it throws — there's no Keychain/Keystore
// equivalent in a browser), so on web this falls back to localStorage instead. That's the
// standard Expo pattern for this gap, not a security regression for v1: the app's real distribution
// target is native (iOS/Android, per docs/MP-001's scope), and the browser's storage isolation
// model is a different (same-origin, not cross-app) threat model than the one SecureStore guards
// against on native. Without this branch the web build never leaves its loading spinner — see the
// caught TypeError from SecureStore.getItemAsync during session recovery (found by actually
// running `expo start --web` and driving it in a browser, not by any unit test).
//
// Takes `platformOS` as a parameter (rather than reading Platform.OS internally) so the branch is
// testable as a plain function — jest-expo's test environment doesn't simulate the web platform
// well enough to mock Platform.OS itself reliably.
export function createSessionStorage(platformOS: string): SupportedStorage {
  if (platformOS === 'web') {
    return {
      getItem: (key: string) =>
        Promise.resolve(typeof localStorage === 'undefined' ? null : localStorage.getItem(key)),
      setItem: (key: string, value: string) => {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem(key, value);
        }
        return Promise.resolve();
      },
      removeItem: (key: string) => {
        if (typeof localStorage !== 'undefined') {
          localStorage.removeItem(key);
        }
        return Promise.resolve();
      },
    };
  }
  return {
    getItem: (key: string) => SecureStore.getItemAsync(key),
    setItem: (key: string, value: string) => SecureStore.setItemAsync(key, value),
    removeItem: (key: string) => SecureStore.deleteItemAsync(key),
  };
}

const SecureStoreAdapter: SupportedStorage = createSessionStorage(Platform.OS);

const { supabaseUrl, supabaseAnonKey } = Constants.expoConfig?.extra ?? {};

if (!supabaseUrl || !supabaseAnonKey) {
  // Fails fast at startup rather than surfacing as a confusing runtime error the first time a
  // query is made — mirrors MP-014's backend config.py fail-fast behavior. Only names which env
  // vars are missing, never a value (there's no secret here to leak, but same convention).
  throw new Error(
    'Missing EXPO_PUBLIC_SUPABASE_URL / EXPO_PUBLIC_SUPABASE_ANON_KEY. Set them before starting ' +
      'the app — see mobile/app.config.ts and docs/MP-006-MP-012-supabase-setup.md.',
  );
}

// Only the anon key ever reaches the client — the service role key is backend-only (MP-014,
// app.config.ts's own comment). Every query made through this client is subject to the RLS
// policies from MP-013, scoped to whatever user is currently signed in.
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: SecureStoreAdapter,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});
