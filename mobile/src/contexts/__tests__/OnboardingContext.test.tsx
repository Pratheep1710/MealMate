import { act, create } from 'react-test-renderer';

import { OnboardingProvider, useOnboarding } from '../OnboardingContext';

const mockInsert = jest.fn();
const mockRefresh = jest.fn();

jest.mock('../../lib/supabase', () => ({
  supabase: {
    from: () => ({
      insert: (...args: unknown[]) => mockInsert(...args),
    }),
  },
}));

jest.mock('../SessionContext', () => ({
  useSession: () => ({ session: { user: { id: 'user-1' } } }),
}));

jest.mock('../ProfileContext', () => ({
  useProfile: () => ({ refresh: () => mockRefresh() }),
}));

function renderOnboarding() {
  let latest: ReturnType<typeof useOnboarding> | undefined;
  let tree: ReturnType<typeof create> | undefined;
  function Probe() {
    latest = useOnboarding();
    return null;
  }
  act(() => {
    tree = create(
      <OnboardingProvider>
        <Probe />
      </OnboardingProvider>,
    );
  });
  return {
    current: () => latest!,
    unmount: () => act(() => tree!.unmount()),
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockInsert.mockResolvedValue({ error: null });
});

describe('OnboardingContext.submit', () => {
  it('nulls meat_types/nonveg_days_per_week/nonveg_day_pattern for a vegetarian profile', async () => {
    const onboarding = renderOnboarding();
    act(() => {
      onboarding.current().updateDraft({
        dietType: 'vegetarian',
        meatTypes: [],
        nonvegDaysPerWeek: null,
        nonvegDayPattern: [],
        eggFrequency: null,
        eggDayPattern: [],
        allergies: [],
        allergyOtherText: '',
        planningMode: 'suggestion',
        groceryDay: 'monday',
      });
    });

    await act(async () => {
      await onboarding.current().submit();
    });

    expect(mockInsert).toHaveBeenCalledWith(
      expect.objectContaining({
        diet_type: 'vegetarian',
        meat_types: [],
        nonveg_days_per_week: null,
        nonveg_day_pattern: null,
        egg_frequency: null,
        egg_day_pattern: [],
      }),
    );
  });

  it('nulls the meat-quota fields but keeps egg_frequency for an eggetarian profile', async () => {
    const onboarding = renderOnboarding();
    act(() => {
      onboarding.current().updateDraft({
        dietType: 'eggetarian',
        meatTypes: [],
        nonvegDaysPerWeek: null,
        nonvegDayPattern: [],
        eggFrequency: 'any',
        eggDayPattern: [],
        allergies: [],
        allergyOtherText: '',
        planningMode: 'reserves',
        groceryDay: 'saturday',
      });
    });

    await act(async () => {
      await onboarding.current().submit();
    });

    expect(mockInsert).toHaveBeenCalledWith(
      expect.objectContaining({
        diet_type: 'eggetarian',
        meat_types: [],
        nonveg_days_per_week: null,
        nonveg_day_pattern: null,
        egg_frequency: 'any',
      }),
    );
  });

  it('keeps meat_types/nonveg quota fields for a non-vegetarian profile', async () => {
    const onboarding = renderOnboarding();
    act(() => {
      onboarding.current().updateDraft({
        dietType: 'nonvegetarian',
        meatTypes: ['chicken', 'fish'],
        nonvegDaysPerWeek: 2,
        nonvegDayPattern: ['wednesday', 'saturday'],
        eggFrequency: 'nonveg_days',
        eggDayPattern: [],
        allergies: ['Nuts'],
        allergyOtherText: '',
        planningMode: 'suggestion',
        groceryDay: 'sunday',
      });
    });

    await act(async () => {
      await onboarding.current().submit();
    });

    expect(mockInsert).toHaveBeenCalledWith(
      expect.objectContaining({
        diet_type: 'nonvegetarian',
        meat_types: ['chicken', 'fish'],
        nonveg_days_per_week: 2,
        nonveg_day_pattern: ['wednesday', 'saturday'],
        dietary_restrictions: ['Nuts'],
      }),
    );
  });

  it('only submits egg_day_pattern when egg_frequency is specific', async () => {
    const onboarding = renderOnboarding();
    act(() => {
      onboarding.current().updateDraft({
        dietType: 'eggetarian',
        eggFrequency: 'any',
        eggDayPattern: ['monday'], // stale from an earlier "specific" selection, since discarded
        planningMode: 'suggestion',
        groceryDay: 'monday',
      });
    });

    await act(async () => {
      await onboarding.current().submit();
    });

    expect(mockInsert).toHaveBeenCalledWith(
      expect.objectContaining({ egg_frequency: 'any', egg_day_pattern: [] }),
    );
  });

  it("never merges the free-text 'Other' allergy note into dietary_restrictions", async () => {
    const onboarding = renderOnboarding();
    act(() => {
      onboarding.current().updateDraft({
        dietType: 'vegetarian',
        eggFrequency: null,
        allergies: ['Nuts'],
        allergyOtherText: 'shellfish, described by the user in their own words',
        planningMode: 'suggestion',
        groceryDay: 'monday',
      });
    });

    await act(async () => {
      await onboarding.current().submit();
    });

    const payload = mockInsert.mock.calls[0][0];
    expect(payload.dietary_restrictions).toEqual(['Nuts']);
    expect(payload.allergy_other_text).toBe('shellfish, described by the user in their own words');
    expect(JSON.stringify(payload.dietary_restrictions)).not.toContain('shellfish');
  });

  it('refreshes the profile context after a successful insert', async () => {
    const onboarding = renderOnboarding();
    act(() => {
      onboarding.current().updateDraft({
        dietType: 'vegetarian',
        eggFrequency: null,
        planningMode: 'suggestion',
        groceryDay: 'monday',
      });
    });

    await act(async () => {
      await onboarding.current().submit();
    });

    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it('surfaces an insert error without refreshing the profile', async () => {
    mockInsert.mockResolvedValue({ error: { message: 'insert failed' } });
    const onboarding = renderOnboarding();
    act(() => {
      onboarding.current().updateDraft({
        dietType: 'vegetarian',
        eggFrequency: null,
        planningMode: 'suggestion',
        groceryDay: 'monday',
      });
    });

    let result: { error: string | null } | undefined;
    await act(async () => {
      result = await onboarding.current().submit();
    });

    expect(result?.error).toBe('insert failed');
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('rejects submit before every required question is answered', async () => {
    const onboarding = renderOnboarding();

    let result: { error: string | null } | undefined;
    await act(async () => {
      result = await onboarding.current().submit();
    });

    expect(result?.error).toBeTruthy();
    expect(mockInsert).not.toHaveBeenCalled();
  });
});
