import { act, create } from 'react-test-renderer';

import App from './App';

// MP-021/MP-022/MP-023 smoke test: the app mounts without throwing, wired through the real
// navigation and context providers. The Supabase client itself is mocked so this stays a fast,
// deterministic unit test rather than making a real network call to a fake project URL.
jest.mock('./src/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: () => Promise.resolve({ data: { session: null } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signInWithPassword: () => Promise.resolve({ error: null }),
      signOut: () => Promise.resolve(),
    },
  },
}));

test('renders without crashing', async () => {
  let tree: ReturnType<typeof create>;
  await act(async () => {
    tree = create(<App />);
  });
  expect(tree!.toJSON()).toBeTruthy();
});
