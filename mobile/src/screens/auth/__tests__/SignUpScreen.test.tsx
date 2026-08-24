import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { act, create } from 'react-test-renderer';

import type { AuthStackParamList } from '../../../navigation/types';
import { SignUpScreen } from '../SignUpScreen';

const mockSignUp = jest.fn();
const mockNavigate = jest.fn();

jest.mock('../../../contexts/SessionContext', () => ({
  useSession: () => ({ signUp: mockSignUp }),
}));

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
          <Stack.Screen name="SignUp" component={SignUpScreen} />
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

describe('SignUpScreen', () => {
  it('calls signUp with the entered email and password', async () => {
    mockSignUp.mockResolvedValue({ error: null, needsConfirmation: false });
    const tree = await renderScreen();

    const emailInput = tree.root.findByProps({ testID: 'sign-up-email' });
    const passwordInput = tree.root.findByProps({ testID: 'sign-up-password' });
    const submit = tree.root.findByProps({ testID: 'sign-up-submit' });

    await act(async () => {
      emailInput.props.onChangeText('new@example.com');
      passwordInput.props.onChangeText('a-strong-password');
    });
    await act(async () => {
      submit.props.onPress();
    });

    expect(mockSignUp).toHaveBeenCalledWith('new@example.com', 'a-strong-password');
  });

  it('shows the check-your-email state when confirmation is required', async () => {
    mockSignUp.mockResolvedValue({ error: null, needsConfirmation: true });
    const tree = await renderScreen();

    const emailInput = tree.root.findByProps({ testID: 'sign-up-email' });
    const passwordInput = tree.root.findByProps({ testID: 'sign-up-password' });
    const submit = tree.root.findByProps({ testID: 'sign-up-submit' });

    await act(async () => {
      emailInput.props.onChangeText('new@example.com');
      passwordInput.props.onChangeText('a-strong-password');
    });
    await act(async () => {
      submit.props.onPress();
    });

    expect(textOf(tree)).toContain('Check your email');
  });

  it('surfaces a signup error instead of silently failing', async () => {
    mockSignUp.mockResolvedValue({ error: 'Email already registered', needsConfirmation: false });
    const tree = await renderScreen();

    const emailInput = tree.root.findByProps({ testID: 'sign-up-email' });
    const passwordInput = tree.root.findByProps({ testID: 'sign-up-password' });
    const submit = tree.root.findByProps({ testID: 'sign-up-submit' });

    await act(async () => {
      emailInput.props.onChangeText('taken@example.com');
      passwordInput.props.onChangeText('a-strong-password');
    });
    await act(async () => {
      submit.props.onPress();
    });

    expect(textOf(tree)).toContain('Email already registered');
  });

  it('disables submit until both fields are filled with a valid-length password', async () => {
    const tree = await renderScreen();
    const submit = tree.root.findByProps({ testID: 'sign-up-submit' });

    expect(submit.props.disabled).toBe(true);

    const emailInput = tree.root.findByProps({ testID: 'sign-up-email' });
    const passwordInput = tree.root.findByProps({ testID: 'sign-up-password' });
    await act(async () => {
      emailInput.props.onChangeText('new@example.com');
      passwordInput.props.onChangeText('short');
    });

    expect(tree.root.findByProps({ testID: 'sign-up-submit' }).props.disabled).toBe(true);
  });
});
