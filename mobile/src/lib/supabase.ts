import 'react-native-url-polyfill/auto';

import { createClient, type SupportedStorage } from '@supabase/supabase-js';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

// MP-023: session tokens must never sit in plaintext storage. expo-secure-store is backed by the
// iOS Keychain / Android Keystore, not AsyncStorage — this adapter is the only place session data
// touches disk, so there is exactly one path to audit for that guarantee.
const SecureStoreAdapter: SupportedStorage = {
  getItem: (key: string) => SecureStore.getItemAsync(key),
  setItem: (key: string, value: string) => SecureStore.setItemAsync(key, value),
  removeItem: (key: string) => SecureStore.deleteItemAsync(key),
};

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
