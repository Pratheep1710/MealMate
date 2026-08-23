import { act, create } from 'react-test-renderer';

import App from './App';

// MP-021 smoke test: the app mounts without throwing.
test('renders without crashing', () => {
  let tree: ReturnType<typeof create>;
  act(() => {
    tree = create(<App />);
  });
  expect(tree!.toJSON()).toBeTruthy();
});
