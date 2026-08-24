import type { Session } from '@supabase/supabase-js';
import { act, create } from 'react-test-renderer';

import { useSession, SessionProvider } from '../SessionContext';

const mockSession = {
  user: { id: 'user-1', email: 'user@example.com' },
  access_token: 'token',
} as unknown as Session;

let mockAuthStateCallback: ((event: string, session: unknown) => void) | undefined;
const mockSignInWithPassword = jest.fn();
const mockSignUp = jest.fn();
const mockSignOut = jest.fn();
const mockGetSession = jest.fn();
const mockUnsubscribe = jest.fn();

jest.mock('../../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]) => mockGetSession(...args),
      signInWithPassword: (...args: unknown[]) => mockSignInWithPassword(...args),
      signUp: (...args: unknown[]) => mockSignUp(...args),
      signOut: (...args: unknown[]) => mockSignOut(...args),
      onAuthStateChange: (cb: (event: string, session: unknown) => void) => {
        mockAuthStateCallback = cb;
        return { data: { subscription: { unsubscribe: mockUnsubscribe } } };
      },
    },
  },
}));

// Returns a live accessor (not a destructured snapshot) so assertions taken after a later
// act() — e.g. an onAuthStateChange event — see the current context value, not the one captured
// at mount time.
function renderSession() {
  let latest: ReturnType<typeof useSession> | undefined;
  let tree: ReturnType<typeof create> | undefined;
  return {
    async mount() {
      await act(async () => {
        tree = create(
          <SessionProvider>
            <Probe onValue={(value) => (latest = value)} />
          </SessionProvider>,
        );
      });
    },
    current(): ReturnType<typeof useSession> {
      return latest!;
    },
    unmount() {
      act(() => {
        tree!.unmount();
      });
    },
  };
}

function Probe({ onValue }: { onValue: (value: ReturnType<typeof useSession>) => void }) {
  onValue(useSession());
  return null;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockAuthStateCallback = undefined;
  mockGetSession.mockResolvedValue({ data: { session: null } });
});

describe('SessionProvider', () => {
  it('starts initializing, then resolves to no session when none is persisted', async () => {
    const rendered = renderSession();
    await rendered.mount();
    expect(rendered.current().initializing).toBe(false);
    expect(rendered.current().session).toBeNull();
  });

  it('picks up a persisted session on mount', async () => {
    mockGetSession.mockResolvedValue({ data: { session: mockSession } });
    const rendered = renderSession();
    await rendered.mount();
    expect(rendered.current().session).toEqual(mockSession);
  });

  it('updates session state on sign-in via onAuthStateChange', async () => {
    const rendered = renderSession();
    await rendered.mount();
    expect(rendered.current().session).toBeNull();

    await act(async () => {
      mockAuthStateCallback?.('SIGNED_IN', mockSession);
    });

    expect(rendered.current().session).toEqual(mockSession);
  });

  it('clears session state on sign-out via onAuthStateChange', async () => {
    mockGetSession.mockResolvedValue({ data: { session: mockSession } });
    const rendered = renderSession();
    await rendered.mount();
    expect(rendered.current().session).toEqual(mockSession);

    await act(async () => {
      mockAuthStateCallback?.('SIGNED_OUT', null);
    });

    expect(rendered.current().session).toBeNull();
  });

  it('reflects a token refresh event (session refresh, not just login/logout)', async () => {
    mockGetSession.mockResolvedValue({ data: { session: mockSession } });
    const rendered = renderSession();
    await rendered.mount();
    const refreshed = { ...mockSession, access_token: 'refreshed-token' } as unknown as Session;

    await act(async () => {
      mockAuthStateCallback?.('TOKEN_REFRESHED', refreshed);
    });

    expect(rendered.current().session).toEqual(refreshed);
  });

  it('signInWithPassword delegates to supabase and surfaces an error message', async () => {
    mockSignInWithPassword.mockResolvedValue({ error: { message: 'Invalid credentials' } });
    const rendered = renderSession();
    await rendered.mount();

    const result = await rendered
      .current()
      .signInWithPassword('user@example.com', 'wrong-password');

    expect(mockSignInWithPassword).toHaveBeenCalledWith({
      email: 'user@example.com',
      password: 'wrong-password',
    });
    expect(result.error).toBe('Invalid credentials');
  });

  it('signUp reports needsConfirmation when the project requires email confirmation', async () => {
    mockSignUp.mockResolvedValue({ data: { session: null }, error: null });
    const rendered = renderSession();
    await rendered.mount();

    const result = await rendered.current().signUp('new@example.com', 'a-strong-password');

    expect(mockSignUp).toHaveBeenCalledWith({
      email: 'new@example.com',
      password: 'a-strong-password',
    });
    expect(result).toEqual({ error: null, needsConfirmation: true });
  });

  it('signUp reports no confirmation needed when the project auto-confirms and starts a session', async () => {
    mockSignUp.mockResolvedValue({ data: { session: mockSession }, error: null });
    const rendered = renderSession();
    await rendered.mount();

    const result = await rendered.current().signUp('new@example.com', 'a-strong-password');

    expect(result).toEqual({ error: null, needsConfirmation: false });
  });

  it('signUp surfaces an error message and does not claim confirmation is needed', async () => {
    mockSignUp.mockResolvedValue({
      data: { session: null },
      error: { message: 'Email already registered' },
    });
    const rendered = renderSession();
    await rendered.mount();

    const result = await rendered.current().signUp('taken@example.com', 'a-strong-password');

    expect(result).toEqual({ error: 'Email already registered', needsConfirmation: false });
  });

  it('signOut delegates to supabase', async () => {
    const rendered = renderSession();
    await rendered.mount();
    await rendered.current().signOut();
    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });

  it('unsubscribes the auth listener on unmount', async () => {
    const rendered = renderSession();
    await rendered.mount();
    rendered.unmount();
    expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
  });
});
