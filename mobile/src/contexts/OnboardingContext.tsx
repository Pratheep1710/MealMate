import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

import { triggerGeneration } from '../lib/backendClient';
import { supabase } from '../lib/supabase';
import type { DayName, DietType, EggFrequency, MeatType } from '../lib/onboardingVocabulary';
import { useProfile } from './ProfileContext';
import { useSession } from './SessionContext';

// Phase 8 (MP-024/025/026): the in-progress draft of onboarding answers, lifted here so every
// question screen can read/update it across navigation the same way ProfileContext/SessionContext
// are shared elsewhere in this codebase. Only submit() ever writes to Supabase — each screen just
// updates local draft state and navigates on.
export type OnboardingDraft = {
  dietType: DietType | null;
  meatTypes: MeatType[];
  nonvegDaysPerWeek: number | null;
  nonvegDayPattern: DayName[];
  eggFrequency: EggFrequency | null;
  eggDayPattern: DayName[];
  allergies: string[];
  allergyOtherText: string;
  planningMode: 'suggestion' | 'reserves' | null;
  groceryDay: DayName | null;
};

const EMPTY_DRAFT: OnboardingDraft = {
  dietType: null,
  meatTypes: [],
  nonvegDaysPerWeek: null,
  nonvegDayPattern: [],
  eggFrequency: null,
  eggDayPattern: [],
  allergies: [],
  allergyOtherText: '',
  planningMode: null,
  groceryDay: null,
};

type OnboardingContextValue = {
  draft: OnboardingDraft;
  updateDraft: (patch: Partial<OnboardingDraft>) => void;
  submit: () => Promise<{ error: string | null }>;
};

const OnboardingContext = createContext<OnboardingContextValue | undefined>(undefined);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { session } = useSession();
  const { refresh } = useProfile();
  const [draft, setDraft] = useState<OnboardingDraft>(EMPTY_DRAFT);

  const value = useMemo<OnboardingContextValue>(
    () => ({
      draft,
      updateDraft: (patch) => setDraft((current) => ({ ...current, ...patch })),
      submit: async () => {
        if (!session) {
          return { error: 'No signed-in user to submit onboarding for.' };
        }
        if (!draft.dietType || !draft.planningMode || !draft.groceryDay) {
          return { error: 'Please answer every question before continuing.' };
        }
        const isNonveg = draft.dietType === 'nonvegetarian';
        // A single INSERT, never an upsert-with-update-semantics — planning_mode is DB-enforced
        // insert-only (0009_protect_planning_mode.sql), so onboarding must be a one-shot write.
        const { error } = await supabase.from('user_profiles').insert({
          id: session.user.id,
          diet_type: draft.dietType,
          meat_types: isNonveg ? draft.meatTypes : [],
          nonveg_days_per_week: isNonveg ? draft.nonvegDaysPerWeek : null,
          nonveg_day_pattern: isNonveg ? draft.nonvegDayPattern : null,
          egg_frequency: draft.dietType === 'vegetarian' ? null : draft.eggFrequency,
          egg_day_pattern: draft.eggFrequency === 'specific' ? draft.eggDayPattern : [],
          dietary_restrictions: draft.allergies,
          allergy_other_text: draft.allergyOtherText.trim() || null,
          planning_mode: draft.planningMode,
          grocery_day: draft.groceryDay,
        });
        if (error) {
          return { error: error.message };
        }
        // MP-094: fires the real generation trigger right away, best-effort. Never awaited and
        // never lets its rejection surface as an onboarding error — offline, the backend not
        // being deployed yet, or a transient failure must not block onboarding completion; the
        // scheduled sweep (run_weekly_generation.py) still generates this user's first plan on
        // its own schedule if this call never lands.
        triggerGeneration().catch(() => {});
        await refresh();
        return { error: null };
      },
    }),
    [draft, session, refresh],
  );

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>;
}

export function useOnboarding(): OnboardingContextValue {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error('useOnboarding must be used within an OnboardingProvider');
  }
  return context;
}
