import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { act, create } from 'react-test-renderer';

import type { AuthStackParamList } from '../../../navigation/types';
import { PhonePreviewScreen } from '../PhonePreviewScreen';

const mockNavigate = jest.fn();
const mockGoBack = jest.fn();

jest.mock('@react-navigation/native', () => {
  const actual = jest.requireActual('@react-navigation/native');
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate, goBack: mockGoBack }),
  };
});

const Stack = createNativeStackNavigator<AuthStackParamList>();

async function renderScreen() {
  let tree: ReturnType<typeof create>;
  await act(async () => {
    tree = create(
      <NavigationContainer>
        <Stack.Navigator>
          <Stack.Screen name="PhonePreview" component={PhonePreviewScreen} />
        </Stack.Navigator>
      </NavigationContainer>,
    );
  });
  return tree!;
}

function textOf(tree: ReturnType<typeof create>): string {
  return JSON.stringify(tree.toJSON());
}

function tapKey(tree: ReturnType<typeof create>, digit: string) {
  const key = tree.root.findByProps({ testID: `phone-preview-key-${digit}` });
  act(() => {
    key.props.onPress();
  });
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('PhonePreviewScreen', () => {
  it('is labeled as a preview, not a real sign-in path', async () => {
    const tree = await renderScreen();
    expect(textOf(tree)).toContain('Preview');
  });

  it('advances to the OTP step once ten digits are entered and "Send the code" is pressed', async () => {
    const tree = await renderScreen();

    for (const d of '9876543210') {
      tapKey(tree, d);
    }
    const primary = tree.root.findByProps({ testID: 'phone-preview-primary' });
    await act(async () => {
      primary.props.onPress();
    });

    expect(textOf(tree)).toContain('Enter the code');
  });

  it('auto-advances to the done step once six OTP digits are entered', async () => {
    jest.useFakeTimers();
    const tree = await renderScreen();

    for (const d of '9876543210') {
      tapKey(tree, d);
    }
    await act(async () => {
      tree.root.findByProps({ testID: 'phone-preview-primary' }).props.onPress();
    });
    for (const d of '123456') {
      tapKey(tree, d);
    }
    await act(async () => {
      jest.advanceTimersByTime(500);
    });

    expect(textOf(tree)).toContain("You're in.");
    expect(textOf(tree)).toContain('nothing was actually created');
    jest.useRealTimers();
  });

  it("the done step's CTA exits to real sign-in rather than entering the app", async () => {
    jest.useFakeTimers();
    const tree = await renderScreen();

    for (const d of '9876543210') {
      tapKey(tree, d);
    }
    await act(async () => {
      tree.root.findByProps({ testID: 'phone-preview-primary' }).props.onPress();
    });
    for (const d of '123456') {
      tapKey(tree, d);
    }
    await act(async () => {
      jest.advanceTimersByTime(500);
    });
    jest.useRealTimers();

    const cta = tree.root.findByProps({ testID: 'phone-preview-done-cta' });
    await act(async () => {
      cta.props.onPress();
    });

    expect(mockNavigate).toHaveBeenCalledWith('SignIn');
  });

  it('delete removes the last digit typed', async () => {
    const tree = await renderScreen();

    tapKey(tree, '9');
    tapKey(tree, '8');
    const del = tree.root.findByProps({ testID: 'phone-preview-delete' });
    act(() => {
      del.props.onPress();
    });

    const digits = tree.root.findByProps({ testID: 'phone-preview-digits' });
    expect(digits.props.children).toBe('9');
  });
});
