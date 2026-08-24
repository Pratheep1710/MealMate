// MP-022: route param lists, one per navigator. Centralized here (not inline per-navigator) so a
// screen added to one stack can't silently drift from what useNavigation<>() expects elsewhere.

export type AuthStackParamList = {
  SignIn: undefined;
};

export type OnboardingStackParamList = {
  // Single placeholder step — MP-024 (the 8-question flow) defines the real steps; this stack
  // exists so onboarding has a route today without hardcoding its internals ahead of that spec.
  OnboardingStart: undefined;
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
