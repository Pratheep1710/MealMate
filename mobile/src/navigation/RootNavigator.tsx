import { NavigationContainer } from '@react-navigation/native';
import { ActivityIndicator, View } from 'react-native';

import { useProfile } from '../contexts/ProfileContext';
import { useSession } from '../contexts/SessionContext';
import { AuthNavigator } from './AuthNavigator';
import { MainTabNavigator } from './MainTabNavigator';
import { OnboardingNavigator } from './OnboardingNavigator';

// MP-022's state boundary: exactly one of these three navigator trees is mounted at a time,
// switched on session/profile state rather than nested as sibling screens a user could navigate
// between directly — that's what keeps this non-circular (AC: "no circular navigation"). A signed
// -out user cannot reach Onboarding or the main tabs by navigating; only a session change swaps
// the tree.
export function RootNavigator() {
  const { session, initializing } = useSession();
  const { hasCompletedOnboarding } = useProfile();

  if (initializing || (session && hasCompletedOnboarding === null)) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <NavigationContainer>
      {!session ? (
        <AuthNavigator />
      ) : hasCompletedOnboarding ? (
        <MainTabNavigator />
      ) : (
        <OnboardingNavigator />
      )}
    </NavigationContainer>
  );
}
