import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { act, create } from 'react-test-renderer';

import type { OnboardingStackParamList } from '../../../navigation/types';
import { AllergiesScreen } from '../AllergiesScreen';

const mockUpdateDraft = jest.fn();
const mockNavigate = jest.fn();

jest.mock('../../../contexts/OnboardingContext', () => ({
  useOnboarding: () => ({
    draft: { allergies: [], allergyOtherText: '' },
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
          <Stack.Screen name="Allergies" component={AllergiesScreen} />
        </Stack.Navigator>
      </NavigationContainer>,
    );
  });
  return tree!;
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('AllergiesScreen', () => {
  it('defaults to "None" selected since no allergy or other text was set', async () => {
    const tree = await renderScreen();
    expect(tree.root.findByProps({ testID: 'onboarding-allergies-none' }).props.selected).toBe(
      true,
    );
  });

  it('picking a specific allergy clears "None"', async () => {
    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'onboarding-allergies-Nuts' }).props.onPress();
    });

    expect(tree.root.findByProps({ testID: 'onboarding-allergies-Nuts' }).props.selected).toBe(
      true,
    );
    expect(tree.root.findByProps({ testID: 'onboarding-allergies-none' }).props.selected).toBe(
      false,
    );
  });

  it('picking "None" after selecting allergies clears them and any Other text', async () => {
    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'onboarding-allergies-Nuts' }).props.onPress();
      tree.root.findByProps({ testID: 'onboarding-allergies-other' }).props.onPress();
    });
    await act(async () => {
      tree.root
        .findByProps({ testID: 'onboarding-allergies-other-text' })
        .props.onChangeText('a rare spice allergy');
    });
    await act(async () => {
      tree.root.findByProps({ testID: 'onboarding-allergies-none' }).props.onPress();
    });

    expect(tree.root.findByProps({ testID: 'onboarding-allergies-Nuts' }).props.selected).toBe(
      false,
    );
    expect(tree.root.findAllByProps({ testID: 'onboarding-allergies-other-text' })).toHaveLength(0);

    await act(async () => {
      tree.root.findByProps({ testID: 'onboarding-allergies-continue' }).props.onPress();
    });
    expect(mockUpdateDraft).toHaveBeenCalledWith(
      expect.objectContaining({ allergies: [], allergyOtherText: '' }),
    );
  });

  it('lets continue proceed with nothing selected at all (an unanswered Q5 still submits)', async () => {
    const tree = await renderScreen();
    expect(tree.root.findByProps({ testID: 'onboarding-allergies-continue' }).props.disabled).toBe(
      false,
    );
  });
});
