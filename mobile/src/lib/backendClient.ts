import Constants from 'expo-constants';

import { supabase } from './supabase';

// Phase 9 (MP-092/093/094): the live backend (render.yaml, backend/app/routes.py) the mobile
// client calls right after onboarding — see OnboardingContext.submit() for the trigger call and
// WeekPlanScreen for the instant-fallback read. Same fail-fast contract as supabase.ts: a missing
// EXPO_PUBLIC_BACKEND_URL fails app startup with a clear message, never a silent null base URL.
const backendUrl = Constants.expoConfig?.extra?.backendUrl as string | undefined;

if (!backendUrl) {
  throw new Error(
    'Missing EXPO_PUBLIC_BACKEND_URL. Set it before starting the app — see mobile/app.config.ts.',
  );
}

const REQUEST_TIMEOUT_MS = 10_000;

export type TriggerGenerationResponse = {
  week_start: string;
};

export type InstantFallbackItem = {
  day: string;
  slot: string;
  item_type: string;
  dish_id: string | null;
  dish_name: string | null;
};

async function authorizedRequest(path: string, init: RequestInit): Promise<Response> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const accessToken = session?.access_token;
  if (!accessToken) {
    throw new Error(`No active session — cannot call ${path}`);
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${backendUrl}${path}`, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${accessToken}` },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Backend request to ${path} failed with status ${response.status}`);
    }
    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}

/** MP-094: fires the onboarding-completion generation trigger. Best-effort by design — callers
 * (OnboardingContext.submit()) must never let a failure here block onboarding completion; the
 * scheduled sweep (backend/scripts/run_weekly_generation.py) still generates this user's first
 * plan on its own schedule if this call never lands.
 */
export async function triggerGeneration(): Promise<TriggerGenerationResponse> {
  const response = await authorizedRequest('/generation/trigger', { method: 'POST' });
  return (await response.json()) as TriggerGenerationResponse;
}

/** MP-093: the instant, zero-LLM fallback meals for the next 1-2 slots, rendered by
 * WeekPlanScreen while MP-094's real generation is still running.
 */
export async function getInstantFallback(): Promise<InstantFallbackItem[]> {
  const response = await authorizedRequest('/plan/instant-fallback', { method: 'GET' });
  return (await response.json()) as InstantFallbackItem[];
}
