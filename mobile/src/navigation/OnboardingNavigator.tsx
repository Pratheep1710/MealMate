import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { OnboardingProvider } from '../contexts/OnboardingContext';
import { AllergiesScreen } from '../screens/onboarding/AllergiesScreen';
import { DietTypeScreen } from '../screens/onboarding/DietTypeScreen';
import { EggFrequencyScreen } from '../screens/onboarding/EggFrequencyScreen';
import { GroceryDayScreen } from '../screens/onboarding/GroceryDayScreen';
import { MeatTypesScreen } from '../screens/onboarding/MeatTypesScreen';
import { NonvegDaysScreen } from '../screens/onboarding/NonvegDaysScreen';
import { PlanningModeScreen } from '../screens/onboarding/PlanningModeScreen';
import { ReviewScreen } from '../screens/onboarding/ReviewScreen';
import type { OnboardingStackParamList } from './types';

const Stack = createNativeStackNavigator<OnboardingStackParamList>();

// Phase 8 (MP-024): the real 7-question onboarding flow, replacing the MP-022 placeholder. Only
// DietType is always the entry point — every other route is reachable only via the branch-aware
// navigate() calls inside each screen (DietTypeScreen, NonvegDaysScreen, EggFrequencyScreen), not
// by any route ever being the initial screen for a branch that shouldn't see it.
export function OnboardingNavigator() {
  return (
    <OnboardingProvider>
      <Stack.Navigator initialRouteName="DietType" screenOptions={{ headerShown: false }}>
        <Stack.Screen name="DietType" component={DietTypeScreen} />
        <Stack.Screen name="MeatTypes" component={MeatTypesScreen} />
        <Stack.Screen name="NonvegDays" component={NonvegDaysScreen} />
        <Stack.Screen name="EggFrequency" component={EggFrequencyScreen} />
        <Stack.Screen name="Allergies" component={AllergiesScreen} />
        <Stack.Screen name="PlanningMode" component={PlanningModeScreen} />
        <Stack.Screen name="GroceryDay" component={GroceryDayScreen} />
        <Stack.Screen name="Review" component={ReviewScreen} />
      </Stack.Navigator>
    </OnboardingProvider>
  );
}
