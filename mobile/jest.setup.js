// Jest never runs the Expo CLI, so app.config.ts's `extra` block (EXPO_PUBLIC_* env -> app
// manifest) never gets evaluated the way it would in a real build — Constants.expoConfig comes
// back without it. Mock expo-constants directly with the shape src/lib/supabase.ts expects,
// otherwise its fail-fast check throws before any test can mount App. Not a live project: no test
// in this repo makes a real network call against it.
jest.mock('expo-constants', () => ({
  __esModule: true,
  default: {
    expoConfig: {
      extra: {
        supabaseUrl: 'https://test.supabase.co',
        supabaseAnonKey: 'test-anon-key',
      },
    },
  },
}));

// Font loading is a real native asset fetch (expo-font -> expo-asset), which the Jest environment
// has no device to perform. Reporting "loaded" immediately keeps App's useFonts gate from hanging
// tests forever waiting on a load that can never happen here — no test in this repo asserts on the
// actual rendered glyphs, only on text content and structure.
jest.mock('expo-font', () => ({
  useFonts: () => [true],
  loadAsync: () => Promise.resolve(),
  isLoaded: () => true,
}));

jest.mock('expo-splash-screen', () => ({
  preventAutoHideAsync: () => Promise.resolve(),
  hideAsync: () => Promise.resolve(),
}));

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
