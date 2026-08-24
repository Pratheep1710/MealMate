import {
  HankenGrotesk_300Light,
  HankenGrotesk_400Regular,
  HankenGrotesk_500Medium,
  HankenGrotesk_600SemiBold,
} from '@expo-google-fonts/hanken-grotesk';
import {
  Newsreader_300Light,
  Newsreader_300Light_Italic,
  Newsreader_400Regular,
  Newsreader_500Medium,
} from '@expo-google-fonts/newsreader';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useCallback } from 'react';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { colors } from './src/theme/tokens';
import { ProfileProvider } from './src/contexts/ProfileContext';
import { SessionProvider } from './src/contexts/SessionContext';
import { RootNavigator } from './src/navigation/RootNavigator';

// The day-spine/typography redesign (Claude Design project b56ee743) leans on Newsreader for dish
// names/headlines and Hanken Grotesk for everything else — held here at the root so every screen
// shares one load, rather than each screen risking a flash of the system font.
void SplashScreen.preventAutoHideAsync();

export default function App() {
  const [fontsLoaded] = useFonts({
    Newsreader_300Light,
    Newsreader_300Light_Italic,
    Newsreader_400Regular,
    Newsreader_500Medium,
    HankenGrotesk_300Light,
    HankenGrotesk_400Regular,
    HankenGrotesk_500Medium,
    HankenGrotesk_600SemiBold,
  });

  const onLayoutRootView = useCallback(async () => {
    if (fontsLoaded) {
      await SplashScreen.hideAsync();
    }
  }, [fontsLoaded]);

  if (!fontsLoaded) {
    return null;
  }

  return (
    <SafeAreaProvider>
      <View style={{ flex: 1, backgroundColor: colors.ground }} onLayout={onLayoutRootView}>
        <SessionProvider>
          <ProfileProvider>
            <RootNavigator />
            <StatusBar style="dark" />
          </ProfileProvider>
        </SessionProvider>
      </View>
    </SafeAreaProvider>
  );
}
