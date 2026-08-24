import AsyncStorage from '@react-native-async-storage/async-storage';

// MP-027 offline state ("Couldn't reach the plan" in the design pass): the last successful fetch
// is cached so a dropped connection has something real to fall back to instead of a bare error —
// "the saved copy carries the day," per the design brief. Keyed generically so any JSON-shaped
// screen payload can use the same cache/read pair.
const CACHE_PREFIX = 'mealmate:cache:';

export type CachedPayload<T> = {
  data: T;
  savedAt: string; // ISO timestamp
};

export async function saveCache<T>(key: string, data: T): Promise<void> {
  const payload: CachedPayload<T> = { data, savedAt: new Date().toISOString() };
  try {
    await AsyncStorage.setItem(CACHE_PREFIX + key, JSON.stringify(payload));
  } catch {
    // Caching is a nice-to-have for the offline fallback, not a correctness requirement — a
    // storage failure here must never block the live render path that already succeeded.
  }
}

export async function loadCache<T>(key: string): Promise<CachedPayload<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_PREFIX + key);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as CachedPayload<T>;
  } catch {
    return null;
  }
}
