// Phase 8 (MP-024): controlled vocabularies for the onboarding questions, mirroring the backend's
// own source of truth exactly (values and casing) — this is a third hand-maintained copy, after
// backend/app/models/dish.py's DIETARY_FLAG_VALUES/MEAT_TYPE_VALUES and
// backend/app/models/profile.py's DIET_TYPE_VALUES/EGG_FREQUENCY_VALUES, since the mobile client
// can't import from the Python package. Keep all three in sync by hand if this vocabulary ever
// changes — the hard-exclusion array-overlap check (Postgres, case-sensitive) depends on it.

export const DIET_TYPE_VALUES = ['vegetarian', 'eggetarian', 'nonvegetarian'] as const;
export type DietType = (typeof DIET_TYPE_VALUES)[number];

export const MEAT_TYPE_VALUES = ['chicken', 'mutton', 'fish', 'seafood', 'other'] as const;
export type MeatType = (typeof MEAT_TYPE_VALUES)[number];

export const EGG_FREQUENCY_VALUES = ['any', 'nonveg_days', 'specific', 'never'] as const;
export type EggFrequency = (typeof EGG_FREQUENCY_VALUES)[number];

// Matches backend/app/models/dish.py's DIETARY_FLAG_VALUES exactly, plus the UI-only "Other"
// (free text, never submitted as a dietary_restrictions value — see allergyOtherText) and "None"
// (a UI affordance for "nothing selected", not a submitted value at all).
export const DIETARY_FLAG_VALUES = [
  'Nuts',
  'Milk-Dairy',
  'Gluten',
  'Egg',
  'Seafood',
  'Sesame',
] as const;
export type DietaryFlag = (typeof DIETARY_FLAG_VALUES)[number];

// Full lowercase day names — the format grocery_day, nonveg_day_pattern, and egg_day_pattern all
// submit. backend/app/services/planning_trigger.py's day-index lookup only accepts the full form
// (unlike nonveg_day_pattern's own normalize_day_name, which also accepts abbreviations) — full
// names avoid that asymmetry entirely for every day-shaped field this client writes.
export const DAY_NAMES = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
] as const;
export type DayName = (typeof DAY_NAMES)[number];

export const DAY_LABELS: Record<DayName, string> = {
  monday: 'Monday',
  tuesday: 'Tuesday',
  wednesday: 'Wednesday',
  thursday: 'Thursday',
  friday: 'Friday',
  saturday: 'Saturday',
  sunday: 'Sunday',
};
