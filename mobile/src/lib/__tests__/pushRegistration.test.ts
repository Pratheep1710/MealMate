// MP-068: registration must no-op (never throw) on every failure mode — simulator, permission
// denied, no EAS project id, and Expo API failure — since it's a background nicety on app launch,
// not something that should ever block or crash the app.

import { registerForPushNotificationsAsync, syncPushToken } from '../pushRegistration';

const mockIsDevice = { value: true };
jest.mock('expo-device', () => ({
  get isDevice() {
    return mockIsDevice.value;
  },
}));

const mockGetPermissionsAsync = jest.fn();
const mockRequestPermissionsAsync = jest.fn();
const mockGetExpoPushTokenAsync = jest.fn();
const mockSetNotificationChannelAsync = jest.fn();
jest.mock('expo-notifications', () => ({
  getPermissionsAsync: (...args: unknown[]) => mockGetPermissionsAsync(...args),
  requestPermissionsAsync: (...args: unknown[]) => mockRequestPermissionsAsync(...args),
  getExpoPushTokenAsync: (...args: unknown[]) => mockGetExpoPushTokenAsync(...args),
  setNotificationChannelAsync: (...args: unknown[]) => mockSetNotificationChannelAsync(...args),
  AndroidImportance: { MAX: 5 },
}));

jest.mock('expo-constants', () => ({
  __esModule: true,
  default: {
    expoConfig: {
      extra: {
        supabaseUrl: 'https://test.supabase.co',
        supabaseAnonKey: 'test-anon-key',
        eas: { projectId: 'test-project-id' },
      },
    },
  },
}));

const mockRpc = jest.fn((..._args: unknown[]) => Promise.resolve({ error: null }));
jest.mock('../supabase', () => ({
  supabase: { rpc: (...args: unknown[]) => mockRpc(...args) },
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockIsDevice.value = true;
  mockGetPermissionsAsync.mockResolvedValue({ status: 'granted' });
  mockGetExpoPushTokenAsync.mockResolvedValue({ data: 'ExponentPushToken[abc]' });
});

describe('registerForPushNotificationsAsync', () => {
  it('returns null on a simulator without requesting permissions', async () => {
    mockIsDevice.value = false;

    const token = await registerForPushNotificationsAsync();

    expect(token).toBeNull();
    expect(mockGetPermissionsAsync).not.toHaveBeenCalled();
  });

  it('requests permission when not already granted, then returns the token', async () => {
    mockGetPermissionsAsync.mockResolvedValue({ status: 'undetermined' });
    mockRequestPermissionsAsync.mockResolvedValue({ status: 'granted' });

    const token = await registerForPushNotificationsAsync();

    expect(mockRequestPermissionsAsync).toHaveBeenCalled();
    expect(token).toBe('ExponentPushToken[abc]');
  });

  it('returns null when permission is denied', async () => {
    mockGetPermissionsAsync.mockResolvedValue({ status: 'denied' });
    mockRequestPermissionsAsync.mockResolvedValue({ status: 'denied' });

    const token = await registerForPushNotificationsAsync();

    expect(token).toBeNull();
    expect(mockGetExpoPushTokenAsync).not.toHaveBeenCalled();
  });

  it('returns the token on success', async () => {
    const token = await registerForPushNotificationsAsync();
    expect(token).toBe('ExponentPushToken[abc]');
  });

  it('does not throw when the Expo push API call fails', async () => {
    mockGetExpoPushTokenAsync.mockRejectedValue(new Error('network error'));

    await expect(registerForPushNotificationsAsync()).resolves.toBeNull();
  });
});

describe('syncPushToken', () => {
  it('calls the register_push_token RPC with just the token — no user id to get wrong', async () => {
    await syncPushToken('ExponentPushToken[abc]');

    expect(mockRpc).toHaveBeenCalledWith('register_push_token', {
      token: 'ExponentPushToken[abc]',
    });
  });
});
