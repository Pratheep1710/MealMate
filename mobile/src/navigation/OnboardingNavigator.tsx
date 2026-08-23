import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { PlaceholderScreen } from '../screens/PlaceholderScreen';
import type { OnboardingStackParamList } from './types';

const Stack = createNativeStackNavigator<OnboardingStackParamList>();

function OnboardingStartScreen() {
  return (
    <PlaceholderScreen
      title="Let's set up your plan"
      note="The 8-question onboarding flow (MP-024) lands in a later phase."
    />
  );
}

export function OnboardingNavigator() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="OnboardingStart" component={OnboardingStartScreen} />
    </Stack.Navigator>
  );
}
