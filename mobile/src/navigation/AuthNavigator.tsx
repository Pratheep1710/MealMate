import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { LandingScreen } from '../screens/auth/LandingScreen';
import { PhonePreviewScreen } from '../screens/auth/PhonePreviewScreen';
import { SignUpScreen } from '../screens/auth/SignUpScreen';
import { SignInScreen } from '../screens/SignInScreen';
import type { AuthStackParamList } from './types';

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthNavigator() {
  return (
    <Stack.Navigator initialRouteName="Landing" screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Landing" component={LandingScreen} />
      <Stack.Screen name="SignIn" component={SignInScreen} />
      <Stack.Screen name="SignUp" component={SignUpScreen} />
      <Stack.Screen name="PhonePreview" component={PhonePreviewScreen} />
    </Stack.Navigator>
  );
}
