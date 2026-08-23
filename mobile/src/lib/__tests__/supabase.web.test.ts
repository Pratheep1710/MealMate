// MP-023 regression test: expo-secure-store has no web implementation (it throws), which left the
// app stuck on its loading spinner forever on web — caught by actually running the app in a
// browser, not by a unit test. This locks in the localStorage fallback for platformOS === 'web'.
import { createSessionStorage } from '../supabase';

jest.mock('@supabase/supabase-js', () => ({
  createClient: jest.fn(() => ({})),
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(() => Promise.reject(new Error('SecureStore is native-only'))),
  setItemAsync: jest.fn(() => Promise.reject(new Error('SecureStore is native-only'))),
  deleteItemAsync: jest.fn(() => Promise.reject(new Error('SecureStore is native-only'))),
}));

// jest-expo's test environment has no DOM/localStorage (it's native-oriented, not browser-
// oriented) — a minimal in-memory stand-in is enough to prove the adapter round-trips through
// whatever `localStorage` exists at runtime, same as a real browser would provide.
class MemoryLocalStorage {
  private store = new Map<string, string>();
  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  setItem(key: string, value: string) {
    this.store.set(key, value);
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  clear() {
    this.store.clear();
  }
}

describe('createSessionStorage("web")', () => {
  beforeEach(() => {
    (globalThis as unknown as { localStorage: MemoryLocalStorage }).localStorage =
      new MemoryLocalStorage();
  });

  it('uses localStorage instead of expo-secure-store', async () => {
    const storage = createSessionStorage('web');

    await storage.setItem('sb-session', 'token-value');
    await expect(storage.getItem('sb-session')).resolves.toBe('token-value');
    expect(localStorage.getItem('sb-session')).toBe('token-value');

    await storage.removeItem('sb-session');
    await expect(storage.getItem('sb-session')).resolves.toBeNull();
  });
});

describe('createSessionStorage("ios")', () => {
  it('still uses expo-secure-store on native', () => {
    const storage = createSessionStorage('ios');
    expect(storage.getItem('key')).rejects.toThrow('SecureStore is native-only');
  });
});
