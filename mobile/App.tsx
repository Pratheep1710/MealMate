import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ProfileProvider } from './src/contexts/ProfileContext';
import { SessionProvider } from './src/contexts/SessionContext';
import { RootNavigator } from './src/navigation/RootNavigator';

export default function App() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <ProfileProvider>
          <RootNavigator />
          <StatusBar style="auto" />
        </ProfileProvider>
      </SessionProvider>
    </SafeAreaProvider>
  );
}
