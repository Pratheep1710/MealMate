// MP-022: route param lists, one per navigator. Centralized here (not inline per-navigator) so a
// screen added to one stack can't silently drift from what useNavigation<>() expects elsewhere.

export type AuthStackParamList = {
  Landing: undefined;
  SignIn: undefined;
  SignUp: undefined;
  // Phone/OTP sign-in as designed (Claude Design project b56ee743, "Meal Planner Auth.dc.html")
  // isn't backed by a real SMS provider yet — this route is a local-only interaction preview, not
  // a working auth path. See docs/MP-027-design-pass-scope.md.
  PhonePreview: undefined;
};

// Phase 8 (MP-024): the 7-question onboarding flow, per the Phase 8 build brief — not the
// original 8-question functional spec, which this brief supersedes for onboarding purposes.
// Q2 (MeatTypes)/Q3 (NonvegDays) only exist on the Non-vegetarian branch; Q4 (EggFrequency) only
// on the Eggetarian/Non-vegetarian branches. Each screen navigates to the next route by name at
// Continue time (see e.g. DietTypeScreen), so a branch that shouldn't be reachable genuinely
// isn't — not just hidden by styling.
export type OnboardingStackParamList = {
  DietType: undefined;
  MeatTypes: undefined;
  NonvegDays: undefined;
  EggFrequency: undefined;
  Allergies: undefined;
  PlanningMode: undefined;
  GroceryDay: undefined;
  Review: undefined;
};

export type PlanStackParamList = {
  WeekPlan: undefined;
  DayReviewEdit: { planDate: string };
};

export type GroceryStackParamList = {
  GroceryList: undefined;
};

export type SettingsStackParamList = {
  Settings: undefined;
};

export type MainTabParamList = {
  Plan: undefined;
  Grocery: undefined;
  SettingsTab: undefined;
};
