import { NavigationContainer } from '@react-navigation/native';
import { act, create } from 'react-test-renderer';

import { OnboardingNavigator } from '../OnboardingNavigator';

const mockRefresh = jest.fn();

jest.mock('../../contexts/SessionContext', () => ({
  useSession: () => ({ session: { user: { id: 'user-1' } } }),
}));

jest.mock('../../contexts/ProfileContext', () => ({
  useProfile: () => ({ hasCompletedOnboarding: false, refresh: mockRefresh }),
}));

jest.mock('../../lib/supabase', () => ({
  supabase: {
    from: () => ({
      insert: () => Promise.resolve({ error: null }),
    }),
  },
}));

function renderOnboarding() {
  let tree: ReturnType<typeof create>;
  act(() => {
    tree = create(
      <NavigationContainer>
        <OnboardingNavigator />
      </NavigationContainer>,
    );
  });
  return tree!;
}

function findByTestId(tree: ReturnType<typeof create>, testID: string) {
  return tree.root.findAllByProps({ testID }).length > 0;
}

async function press(tree: ReturnType<typeof create>, testID: string) {
  await act(async () => {
    tree.root.findByProps({ testID }).props.onPress();
  });
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('OnboardingNavigator branching (MP-024 AC)', () => {
  it('Vegetarian never mounts MeatTypes, NonvegDays, or EggFrequency', async () => {
    const tree = renderOnboarding();
    expect(findByTestId(tree, 'onboarding-diet-type-vegetarian')).toBe(true);

    await press(tree, 'onboarding-diet-type-vegetarian');
    await press(tree, 'onboarding-diet-type-continue');

    // Genuinely unreachable — these screens' own testIDs are absent from the tree entirely, not
    // just visually hidden.
    expect(findByTestId(tree, 'onboarding-meat-types-chicken')).toBe(false);
    expect(findByTestId(tree, 'onboarding-nonveg-days-count')).toBe(false);
    expect(findByTestId(tree, 'onboarding-egg-frequency-any')).toBe(false);
    // Lands directly on Allergies (Q5).
    expect(findByTestId(tree, 'onboarding-allergies-Nuts')).toBe(true);
  });

  it('Eggetarian reaches EggFrequency but never MeatTypes or NonvegDays', async () => {
    const tree = renderOnboarding();
    await press(tree, 'onboarding-diet-type-eggetarian');
    await press(tree, 'onboarding-diet-type-continue');

    expect(findByTestId(tree, 'onboarding-meat-types-chicken')).toBe(false);
    expect(findByTestId(tree, 'onboarding-nonveg-days-count')).toBe(false);
    expect(findByTestId(tree, 'onboarding-egg-frequency-any')).toBe(true);

    await press(tree, 'onboarding-egg-frequency-any');
    await press(tree, 'onboarding-egg-frequency-continue');
    expect(findByTestId(tree, 'onboarding-allergies-Nuts')).toBe(true);
  });

  it('Non-vegetarian reaches every question in order: MeatTypes, NonvegDays, EggFrequency', async () => {
    const tree = renderOnboarding();
    await press(tree, 'onboarding-diet-type-nonvegetarian');
    await press(tree, 'onboarding-diet-type-continue');

    expect(findByTestId(tree, 'onboarding-meat-types-chicken')).toBe(true);
    await press(tree, 'onboarding-meat-types-chicken');
    await press(tree, 'onboarding-meat-types-continue');

    expect(findByTestId(tree, 'onboarding-nonveg-days-count')).toBe(true);
    await press(tree, 'onboarding-nonveg-days-no-preference');
    await press(tree, 'onboarding-nonveg-days-continue');

    expect(findByTestId(tree, 'onboarding-egg-frequency-any')).toBe(true);
    await press(tree, 'onboarding-egg-frequency-any');
    await press(tree, 'onboarding-egg-frequency-continue');

    expect(findByTestId(tree, 'onboarding-allergies-Nuts')).toBe(true);
  });

  it('walks a full Non-vegetarian run through to a successful submit', async () => {
    const tree = renderOnboarding();
    await press(tree, 'onboarding-diet-type-nonvegetarian');
    await press(tree, 'onboarding-diet-type-continue');
    await press(tree, 'onboarding-meat-types-chicken');
    await press(tree, 'onboarding-meat-types-continue');
    await press(tree, 'onboarding-nonveg-days-no-preference');
    await press(tree, 'onboarding-nonveg-days-continue');
    await press(tree, 'onboarding-egg-frequency-never');
    await press(tree, 'onboarding-egg-frequency-continue');
    await press(tree, 'onboarding-allergies-none');
    await press(tree, 'onboarding-allergies-continue');
    await press(tree, 'onboarding-planning-mode-suggestion');
    await press(tree, 'onboarding-planning-mode-continue');
    await press(tree, 'onboarding-grocery-day-monday');
    await press(tree, 'onboarding-grocery-day-continue');

    expect(findByTestId(tree, 'onboarding-review-continue')).toBe(true);
    await press(tree, 'onboarding-review-continue');

    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });
});
