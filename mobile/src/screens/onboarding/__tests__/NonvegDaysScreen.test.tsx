import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { act, create } from 'react-test-renderer';

import type { OnboardingStackParamList } from '../../../navigation/types';
import { NonvegDaysScreen } from '../NonvegDaysScreen';

const mockUpdateDraft = jest.fn();
const mockNavigate = jest.fn();

jest.mock('../../../contexts/OnboardingContext', () => ({
  useOnboarding: () => ({
    draft: { nonvegDaysPerWeek: null, nonvegDayPattern: [] },
    updateDraft: mockUpdateDraft,
  }),
}));

jest.mock('@react-navigation/native', () => {
  const actual = jest.requireActual('@react-navigation/native');
  return { ...actual, useNavigation: () => ({ navigate: mockNavigate }) };
});

const Stack = createNativeStackNavigator<OnboardingStackParamList>();

async function renderScreen() {
  let tree: ReturnType<typeof create>;
  await act(async () => {
    tree = create(
      <NavigationContainer>
        <Stack.Navigator>
          <Stack.Screen name="NonvegDays" component={NonvegDaysScreen} />
        </Stack.Navigator>
      </NavigationContainer>,
    );
  });
  return tree!;
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('NonvegDaysScreen', () => {
  it('defaults to "No preference" and allows continuing without picking any day', async () => {
    const tree = await renderScreen();
    const continueButton = tree.root.findByProps({ testID: 'onboarding-nonveg-days-continue' });

    expect(
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-no-preference' }).props.selected,
    ).toBe(true);
    expect(continueButton.props.disabled).toBe(false);
    expect(tree.root.findAllByProps({ testID: 'onboarding-nonveg-days-picker' })).toHaveLength(0);
  });

  it('blocks continue until the picked days exactly match the stepper count', async () => {
    const tree = await renderScreen();

    await act(async () => {
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-pick-specific' }).props.onPress();
    });
    expect(
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-continue' }).props.disabled,
    ).toBe(true);

    // Default stepper count is 3 — picking only one day should still block continue.
    await act(async () => {
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-day-wednesday' }).props.onPress();
    });
    expect(
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-continue' }).props.disabled,
    ).toBe(true);

    await act(async () => {
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-day-saturday' }).props.onPress();
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-day-sunday' }).props.onPress();
    });
    expect(
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-continue' }).props.disabled,
    ).toBe(false);
  });

  it('submits an empty pattern when "No preference" is kept, per the lighter-tap default', async () => {
    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'onboarding-nonveg-days-continue' }).props.onPress();
    });

    expect(mockUpdateDraft).toHaveBeenCalledWith(
      expect.objectContaining({ nonvegDaysPerWeek: 3, nonvegDayPattern: [] }),
    );
    expect(mockNavigate).toHaveBeenCalledWith('EggFrequency');
  });
});
