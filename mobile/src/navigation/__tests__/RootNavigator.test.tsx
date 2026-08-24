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

    expect(textOf(tree)).toContain('Meal Planner');
  });

  it('shows a loading state while the session is still initializing', () => {
    mockUseSession.mockReturnValue({ session: null, initializing: true });
    mockUseProfile.mockReturnValue({ hasCompletedOnboarding: null });

    const tree = renderRoot();

    expect(textOf(tree)).not.toContain('Meal Planner');
    expect(textOf(tree)).not.toContain("week's plan");
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

    expect(textOf(tree)).toContain("week's plan");
  });

  it('waits for the profile check to resolve before picking onboarding vs. main tabs', () => {
    mockUseSession.mockReturnValue({
      session: { user: { id: 'user-1' } },
      initializing: false,
    });
    mockUseProfile.mockReturnValue({ hasCompletedOnboarding: null });

    const tree = renderRoot();

    expect(textOf(tree)).not.toContain("Let's set up your plan");
    expect(textOf(tree)).not.toContain("week's plan");
  });
});
