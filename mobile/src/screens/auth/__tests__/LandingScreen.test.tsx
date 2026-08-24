import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { act, create } from 'react-test-renderer';

import type { AuthStackParamList } from '../../../navigation/types';
import { LandingScreen } from '../LandingScreen';

const mockNavigate = jest.fn();

jest.mock('@react-navigation/native', () => {
  const actual = jest.requireActual('@react-navigation/native');
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

const Stack = createNativeStackNavigator<AuthStackParamList>();

async function renderScreen() {
  let tree: ReturnType<typeof create>;
  await act(async () => {
    tree = create(
      <NavigationContainer>
        <Stack.Navigator>
          <Stack.Screen name="Landing" component={LandingScreen} />
        </Stack.Navigator>
      </NavigationContainer>,
    );
  });
  return tree!;
}

function textOf(tree: ReturnType<typeof create>): string {
  return JSON.stringify(tree.toJSON());
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('LandingScreen', () => {
  it('shows the sample day and both real ways in', async () => {
    const tree = await renderScreen();

    expect(textOf(tree)).toContain('Someone already thought about dinner.');
    expect(textOf(tree)).toContain('A Wednesday, for instance');
    expect(textOf(tree)).toContain('Continue with Google');
    expect(textOf(tree)).toContain('Continue with mobile number');
  });

  it('routes "Continue with mobile number" to the phone preview', async () => {
    const tree = await renderScreen();
    const button = tree.root.findByProps({ testID: 'landing-phone' });

    await act(async () => {
      button.props.onPress();
    });

    expect(mockNavigate).toHaveBeenCalledWith('PhonePreview');
  });

  it('routes "Continue with email" to real sign-up', async () => {
    const tree = await renderScreen();
    const button = tree.root.findByProps({ testID: 'landing-email' });

    await act(async () => {
      button.props.onPress();
    });

    expect(mockNavigate).toHaveBeenCalledWith('SignUp');
  });

  it('shows a calm "not set up yet" sheet for Google instead of a fake picker', async () => {
    const tree = await renderScreen();
    const button = tree.root.findByProps({ testID: 'landing-google' });

    await act(async () => {
      button.props.onPress();
    });

    expect(textOf(tree)).toContain("Google sign-in isn't set up yet");
  });
});
