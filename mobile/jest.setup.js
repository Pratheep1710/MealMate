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
