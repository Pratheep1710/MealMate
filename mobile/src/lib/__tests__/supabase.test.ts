// MP-023: verifies the Supabase client is wired to secure, not plaintext, token storage. This is
// a config-shape test (what gets passed to createClient), not a network test.
import { createClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';

// Importing for its module-level side effect: this is what calls createClient(...), which the
// tests below then inspect via the mock's captured call args. jest.mock() calls below are hoisted
// above every import in this file (babel-plugin-jest-hoist), so this still sees the mocks.
import '../supabase';

jest.mock('@supabase/supabase-js', () => ({
  createClient: jest.fn(() => ({})),
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(() => Promise.resolve('stub')),
  setItemAsync: jest.fn(() => Promise.resolve()),
  deleteItemAsync: jest.fn(() => Promise.resolve()),
}));

describe('supabase client configuration', () => {
  it('is created with SecureStore-backed storage, autoRefresh, and persisted sessions', () => {
    expect(createClient).toHaveBeenCalledTimes(1);
    const [, , options] = (createClient as jest.Mock).mock.calls[0];
    expect(options.auth.autoRefreshToken).toBe(true);
    expect(options.auth.persistSession).toBe(true);
    expect(options.auth.storage).toBeDefined();
    expect(options.auth.storage.getItem).not.toBe(undefined);
  });

  it('storage adapter delegates to expo-secure-store, never plaintext AsyncStorage', async () => {
    const [, , options] = (createClient as jest.Mock).mock.calls[0];
    const storage = options.auth.storage;

    await storage.getItem('sb-session');
    await storage.setItem('sb-session', 'token-value');
    await storage.removeItem('sb-session');

    expect(SecureStore.getItemAsync).toHaveBeenCalledWith('sb-session');
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('sb-session', 'token-value');
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('sb-session');
  });
});
