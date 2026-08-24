import AsyncStorage from '@react-native-async-storage/async-storage';

// MP-027 offline state ("Couldn't reach the plan" in the design pass): the last successful fetch
// is cached so a dropped connection has something real to fall back to instead of a bare error —
// "the saved copy carries the day," per the design brief. Keyed generically so any JSON-shaped
// screen payload can use the same cache/read pair.
//
// Scoped to the authenticated user, in both the storage key and the payload: a shared device
// (or a sign-out/sign-in switch without a full app restart) must never let one user's cached meal
// plan render for another. The key scoping means the two users' entries never collide in storage;
// the payload check is the second, independent guard against showing the wrong one, in case a
// caller ever reads a cache under the wrong key.
const CACHE_PREFIX = 'mealmate:cache:';

export type CachedPayload<T> = {
  data: T;
  savedAt: string; // ISO timestamp
  userId: string;
};

function storageKey(key: string, userId: string): string {
  return `${CACHE_PREFIX}${key}:${userId}`;
}

export async function saveCache<T>(key: string, userId: string, data: T): Promise<void> {
  const payload: CachedPayload<T> = { data, savedAt: new Date().toISOString(), userId };
  try {
    await AsyncStorage.setItem(storageKey(key, userId), JSON.stringify(payload));
  } catch {
    // Caching is a nice-to-have for the offline fallback, not a correctness requirement — a
    // storage failure here must never block the live render path that already succeeded.
  }
}

export async function loadCache<T>(key: string, userId: string): Promise<CachedPayload<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(storageKey(key, userId));
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as CachedPayload<T>;
    // Belt-and-suspenders: the key is already user-scoped, but never trust stored data to match
    // its own key without checking — treat any mismatch as no cache at all, not the wrong user's.
    if (parsed.userId !== userId) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/** Clears every cache entry for every user on this device — called on sign-out so a later
 * sign-in (same device, different account) can never read a previous account's cached data. */
export async function clearAllCache(): Promise<void> {
  try {
    const keys = await AsyncStorage.getAllKeys();
    const cacheKeys = keys.filter((k) => k.startsWith(CACHE_PREFIX));
    if (cacheKeys.length > 0) {
      await AsyncStorage.multiRemove(cacheKeys);
    }
  } catch {
    // Best-effort: a failure here shouldn't block sign-out itself.
  }
}
