// Phase 8 (MP-026): mirrors backend/app/services/planning_trigger.py's compute_trigger /
// compute_first_plan_start exactly (same day-before/day-after-grocery_day rule, same
// roll-forward-to-nearest-occurrence approach) — this only needs to *display* a concrete date on
// the Review screen, so it's computed client-side from the answers already collected rather than
// requiring a live backend call the mobile client has no endpoint for (see docs/MP-058-073's
// note on the same constraint for plan-item edits).

import { DAY_NAMES, type DayName } from './onboardingVocabulary';

export type PlanningMode = 'suggestion' | 'reserves';

function dayIndex(day: DayName): number {
  return DAY_NAMES.indexOf(day);
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

// JS Date.getDay(): 0=Sunday..6=Saturday. DAY_NAMES is Monday-first, so this maps to that index.
function weekdayIndex(date: Date): number {
  return (date.getDay() + 6) % 7;
}

function shouldTrigger(candidate: Date, groceryDay: DayName, planningMode: PlanningMode): boolean {
  const offsetDays = planningMode === 'reserves' ? 1 : -1;
  const candidateGroceryDayDate = addDays(candidate, -offsetDays);
  return weekdayIndex(candidateGroceryDayDate) === dayIndex(groceryDay);
}

// Rolls forward from `today` (inclusive) to the nearest date the normal 8 PM sweep would trigger
// generation for this profile. Equals `today` when onboarding happens to land exactly on the
// trigger day; otherwise a concrete date up to 6 days out (the mid-week-signup case).
export function computeFirstPlanStart(
  today: Date,
  groceryDay: DayName,
  planningMode: PlanningMode,
): Date {
  for (let offset = 0; offset < 7; offset += 1) {
    const candidate = addDays(today, offset);
    if (shouldTrigger(candidate, groceryDay, planningMode)) {
      return candidate;
    }
  }
  throw new Error('unreachable: the trigger day recurs at least once every 7 days');
}

export function formatFirstPlanStart(date: Date, today: Date): string {
  const isToday = date.toDateString() === today.toDateString();
  if (isToday) {
    return 'Today';
  }
  return date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
}
