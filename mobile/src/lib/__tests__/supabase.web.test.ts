// MP-023 regression tests for the web storage adapter.
//
// 1. expo-secure-store has no web implementation (it throws), which left the app stuck on its
//    loading spinner forever on web — caught by actually running the app in a browser, not by a
//    unit test.
// 2. The first fix for that used localStorage, which persists tokens in plaintext, readable by
//    any same-origin script — a reviewer caught that this violates MP-023's "no plaintext token
//    storage" AC, which has no web carve-out. This locks in the corrected fix: a non-persistent,
//    in-memory store for platformOS === 'web' that never touches disk at all.
import { createSessionStorage } from '../supabase';

jest.mock('@supabase/supabase-js', () => ({
  createClient: jest.fn(() => ({})),
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(() => Promise.reject(new Error('SecureStore is native-only'))),
  setItemAsync: jest.fn(() => Promise.reject(new Error('SecureStore is native-only'))),
  deleteItemAsync: jest.fn(() => Promise.reject(new Error('SecureStore is native-only'))),
}));

describe('createSessionStorage("web")', () => {
  it('round-trips values through an in-memory store, never expo-secure-store', async () => {
    const storage = createSessionStorage('web');

    await storage.setItem('sb-session', 'token-value');
    await expect(storage.getItem('sb-session')).resolves.toBe('token-value');

    await storage.removeItem('sb-session');
    await expect(storage.getItem('sb-session')).resolves.toBeNull();
  });

  it('never touches localStorage — nothing is written to disk-backed browser storage', async () => {
    const localStorageSpy = { setItem: jest.fn(), getItem: jest.fn(), removeItem: jest.fn() };
    (globalThis as unknown as { localStorage: typeof localStorageSpy }).localStorage =
      localStorageSpy;

    const storage = createSessionStorage('web');
    await storage.setItem('sb-session', 'token-value');
    await storage.getItem('sb-session');
    await storage.removeItem('sb-session');

    expect(localStorageSpy.setItem).not.toHaveBeenCalled();
    expect(localStorageSpy.getItem).not.toHaveBeenCalled();
    expect(localStorageSpy.removeItem).not.toHaveBeenCalled();
  });

  it('does not share state across separate createSessionStorage() instances', async () => {
    const storageA = createSessionStorage('web');
    const storageB = createSessionStorage('web');

    await storageA.setItem('sb-session', 'a-value');

    await expect(storageB.getItem('sb-session')).resolves.toBeNull();
  });
});

describe('createSessionStorage("ios")', () => {
  it('still uses expo-secure-store on native', () => {
    const storage = createSessionStorage('ios');
    expect(storage.getItem('key')).rejects.toThrow('SecureStore is native-only');
  });
});
