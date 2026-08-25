import type { ExpoConfig, ConfigContext } from 'expo/config';

import { loadClientConfig } from './config';

// Environment-specific configuration (MP-021 AC). Only the Supabase URL and anon key belong on
// the client — the service role key, OpenAI key, and Expo access token are backend-only (see
// backend/app/config.py, MP-014, and technical spec §3's auth-boundary note). Values are read
// from env vars at build/start time and exposed to the app via Constants.expoConfig.extra.
// loadClientConfig throws (failing the build/start immediately) if either is missing or invalid —
// see config.ts and its tests for the fail-fast contract this satisfies.
export default ({ config }: ConfigContext): ExpoConfig => {
  const clientConfig = loadClientConfig();

  return {
    ...config,
    name: 'Meal Planner',
    slug: 'pratheep',
    owner: 'pratheeplabss-team',
    version: '1.0.0',
    orientation: 'portrait',
    icon: './assets/icon.png',
    userInterfaceStyle: 'light',
    ios: {
      supportsTablet: true,
    },
    android: {
      adaptiveIcon: {
        backgroundColor: '#E6F4FE',
        foregroundImage: './assets/android-icon-foreground.png',
        backgroundImage: './assets/android-icon-background.png',
        monochromeImage: './assets/android-icon-monochrome.png',
      },
      predictiveBackGestureEnabled: false,
    },
    web: {
      favicon: './assets/favicon.png',
    },
    plugins: ['expo-asset', 'expo-font', 'expo-splash-screen', 'expo-notifications'],
    extra: {
      supabaseUrl: clientConfig.supabaseUrl,
      supabaseAnonKey: clientConfig.supabaseAnonKey,
      eas: {
        projectId: '4a06cb26-500e-4067-bbe6-f8c2fdf50058',
      },
    },
  };
};
