import { act, create } from 'react-test-renderer';

import { RootNavigator } from '../RootNavigator';

const mockUseSession = jest.fn();
const mockUseProfile = jest.fn();

jest.mock('../../contexts/SessionContext', () => ({
  useSession: () => mockUseSession(),
}));

jest.mock('../../contexts/ProfileContext', () => ({
  useProfile: () => mockUseProfile(),
}));

// MP-027/028: the main tab stack now mounts WeekPlanScreen/GroceryListScreen, both of which query
// Supabase on mount. This suite only cares about *which* navigator tree is mounted, not their data
// — mock the client so mounting main tabs doesn't fire a real (and here, doomed-to-fail) network
// call against the fake test URL from jest.setup.js.
jest.mock('../../lib/supabase', () => ({
  supabase: {
    from: () => ({
      select: () => ({
        gte: () => ({
          lte: () => new Promise(() => {}), // never resolves — keeps those screens in "loading"
        }),
      }),
    }),
  },
}));

function renderRoot() {
  let tree: ReturnType<typeof create>;
  act(() => {
    tree = create(<RootNavigator />);
  });
  return tree!;
}

function textOf(tree: ReturnType<typeof create>): string {
  return JSON.stringify(tree.toJSON());
}

describe('RootNavigator state boundary', () => {
  it('shows the auth stack when there is no session', () => {
    mockUseSession.mockReturnValue({ session: null, initializing: false });
    mockUseProfile.mockReturnValue({ hasCompletedOnboarding: null });

    const tree = renderRoot();

    expect(textOf(tree)).toContain('Ennanga Samayal');
  });

  it('shows a loading state while the session is still initializing', () => {
    mockUseSession.mockReturnValue({ session: null, initializing: true });
    mockUseProfile.mockReturnValue({ hasCompletedOnboarding: null });

    const tree = renderRoot();

    expect(textOf(tree)).not.toContain('Ennanga Samayal');
    expect(textOf(tree)).not.toContain('week-plan-loading');
  });

  it('shows onboarding when signed in but no profile exists yet', () => {
    mockUseSession.mockReturnValue({
      session: { user: { id: 'user-1' } },
      initializing: false,
    });
    mockUseProfile.mockReturnValue({ hasCompletedOnboarding: false });

    const tree = renderRoot();

    expect(textOf(tree)).toContain("Let's set up your plan");
  });

  it('shows the main tabs once signed in with a completed profile', () => {
    mockUseSession.mockReturnValue({
      session: { user: { id: 'user-1' } },
      initializing: false,
    });
    mockUseProfile.mockReturnValue({ hasCompletedOnboarding: true });

    const tree = renderRoot();

    expect(textOf(tree)).toContain('week-plan-loading');
  });

  it('waits for the profile check to resolve before picking onboarding vs. main tabs', () => {
    mockUseSession.mockReturnValue({
      session: { user: { id: 'user-1' } },
      initializing: false,
    });
    mockUseProfile.mockReturnValue({ hasCompletedOnboarding: null });

    const tree = renderRoot();

    expect(textOf(tree)).not.toContain("Let's set up your plan");
    expect(textOf(tree)).not.toContain('week-plan-loading');
  });
});
