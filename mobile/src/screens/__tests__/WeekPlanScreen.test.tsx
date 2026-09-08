import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { act, create } from 'react-test-renderer';

import type { PlanStackParamList } from '../../navigation/types';
import { rollingDays } from '../weekPlan/rollingDays';
import { WeekPlanScreen } from '../WeekPlanScreen';

const days = rollingDays(new Date());
const today = days[0].iso;

const mockFrom = jest.fn();
const mockRpc = jest.fn();
const mockUseSession = jest.fn();
const mockRemoveChannel = jest.fn();
const mockGetInstantFallback = jest.fn();

// Realtime channel mock: `.on()` captures the registered callback so tests can fire a synthetic
// postgres_changes event directly, mirroring how the real Supabase client would deliver one.
let capturedRealtimeCallback: ((payload: { new: { status?: string } }) => void) | null = null;
function mockChannel(..._args: unknown[]) {
  const channel: Record<string, unknown> = {};
  channel.on = jest.fn(
    (_event: string, _filter: unknown, callback: typeof capturedRealtimeCallback) => {
      capturedRealtimeCallback = callback;
      return channel;
    },
  );
  channel.subscribe = jest.fn(() => channel);
  return channel;
}

jest.mock('../../lib/supabase', () => ({
  supabase: {
    from: (...args: unknown[]) => mockFrom(...args),
    rpc: (...args: unknown[]) => mockRpc(...args),
    channel: (...args: unknown[]) => mockChannel(...args),
    removeChannel: (...args: unknown[]) => mockRemoveChannel(...args),
  },
}));

jest.mock('../../lib/backendClient', () => ({
  getInstantFallback: (...args: unknown[]) => mockGetInstantFallback(...args),
}));

jest.mock('../../contexts/SessionContext', () => ({
  useSession: () => mockUseSession(),
}));

function chainable(
  result: { data: unknown; error: unknown },
  updateResult: { error: unknown } = { error: null },
) {
  const builder: Record<string, unknown> = {};
  for (const method of ['select', 'gte', 'lte', 'eq', 'in', 'order', 'limit']) {
    builder[method] = jest.fn(() => builder);
  }
  builder.then = (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
    Promise.resolve(result).then(resolve, reject);

  // MP-061: the skip toggle writes via .update(...).eq('id', planId) — a separate sub-builder so
  // its resolved value (updateResult) doesn't collide with the read chain's `result` above.
  const updateBuilder: Record<string, unknown> = {
    eq: jest.fn(() => updateBuilder),
    then: (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
      Promise.resolve(updateResult).then(resolve, reject),
  };
  builder.update = jest.fn(() => updateBuilder);
  builder.__updateBuilder = updateBuilder;
  return builder;
}

const Stack = createNativeStackNavigator<PlanStackParamList>();

function flushAsync(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function renderScreen() {
  let tree: ReturnType<typeof create>;
  await act(async () => {
    tree = create(
      <NavigationContainer>
        <Stack.Navigator>
          <Stack.Screen name="WeekPlan" component={WeekPlanScreen} />
        </Stack.Navigator>
      </NavigationContainer>,
    );
    await flushAsync();
    await flushAsync();
  });
  return tree!;
}

function textOf(tree: ReturnType<typeof create>): string {
  return JSON.stringify(tree.toJSON());
}

// findAllByProps's built-in traversal hits react-navigation's default (unprovided) context getters
// somewhere in this tree shape and throws; a manual predicate walk sidesteps it. Filtered to host
// (string-typed) nodes only — the composite View wrapping each host node also carries the same
// testID prop and would otherwise be double-counted.
function countByTestId(tree: ReturnType<typeof create>, testId: string): number {
  return tree.root.findAll((node) => typeof node.type === 'string' && node.props.testID === testId)
    .length;
}

function todayRow(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'plan-1',
    plan_date: today,
    slot: 'night',
    is_skipped: false,
    plan_items: [
      {
        id: 'item-1',
        item_type: 'rice',
        status: 'filled',
        make_extra: false,
        dishes: { name: 'Sambar Sadam' },
      },
    ],
    ...overrides,
  };
}

beforeEach(async () => {
  jest.clearAllMocks();
  await AsyncStorage.clear();
  capturedRealtimeCallback = null;
  mockUseSession.mockReturnValue({ session: { user: { id: 'user-1' } } });
  mockRpc.mockReturnValue(Promise.resolve({ data: [], error: null }));
  mockGetInstantFallback.mockResolvedValue([]);
});

describe('WeekPlanScreen', () => {
  it('renders a filled slot with the real dish name', async () => {
    mockFrom.mockReturnValue(chainable({ data: [todayRow()], error: null }));

    const tree = await renderScreen();

    expect(mockFrom).toHaveBeenCalledWith('meal_plans');
    expect(textOf(tree)).toContain('Sambar Sadam');
    expect(textOf(tree)).toContain('Today');
  });

  it('shows "Needs a pick" for a needs_manual_pick item', async () => {
    mockFrom.mockReturnValue(
      chainable({
        data: [
          todayRow({
            plan_items: [
              {
                id: 'item-1',
                item_type: 'rice',
                status: 'needs_manual_pick',
                make_extra: false,
                dishes: null,
              },
            ],
          }),
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('Needs a pick');
  });

  it('reads a skipped day as calm, not a warning', async () => {
    mockFrom.mockReturnValue(
      chainable({ data: [todayRow({ is_skipped: true, plan_items: [] })], error: null }),
    );

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('Cooking something of your own');
    expect(textOf(tree)).toContain('your call');
  });

  it('shows the still-cooking skeleton state when today has no plan yet', async () => {
    mockFrom.mockReturnValue(chainable({ data: [], error: null }));

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('Putting today together');
    expect(countByTestId(tree, 'today-skeleton')).toBe(1);
  });

  it('composes rest-of-week rows from real plan items', async () => {
    const tomorrow = days[1].iso;
    mockFrom.mockReturnValue(
      chainable({
        data: [
          {
            id: 'plan-2',
            plan_date: tomorrow,
            slot: 'morning',
            is_skipped: false,
            plan_items: [
              {
                id: 'item-2',
                item_type: 'tiffin',
                status: 'filled',
                make_extra: false,
                dishes: { name: 'Idli' },
              },
            ],
          },
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();

    expect(countByTestId(tree, `rest-of-week-${tomorrow}`)).toBe(1);
    expect(textOf(tree)).toContain('Idli');
  });

  // MP-059: a single-item slot (this fixture's default "night" row has exactly one plan item)
  // offers a real, near-instant quick swap — fetched via list_swap_candidates, not the old inert
  // placeholder copy.
  it('opens the real quick-swap list for a single-item slot', async () => {
    mockFrom.mockReturnValue(chainable({ data: [todayRow()], error: null }));
    mockRpc.mockReturnValue(
      Promise.resolve({
        data: [
          {
            dish_id: 'dish-2',
            name: 'Curd Rice',
            used_this_week: false,
            used_recently: true,
          },
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();
    const slotRow = tree.root.findByProps({ testID: 'slot-row-night' });
    await act(async () => {
      slotRow.props.onPress();
      await flushAsync();
    });

    expect(mockRpc).toHaveBeenCalledWith('list_swap_candidates', {
      target_plan_item_id: 'item-1',
    });
    expect(textOf(tree)).toContain('Curd Rice');
    expect(textOf(tree)).toContain('Used recently');
  });

  // MP-058/060: a multi-item slot (e.g. afternoon's rice+gravy+poriyal) needs per-item choice,
  // which only DayReviewEditScreen offers — this sheet hands off there instead of guessing which
  // item a one-tap swap should target.
  it('offers "Review & edit" instead of a quick swap for a multi-item slot', async () => {
    mockFrom.mockReturnValue(
      chainable({
        data: [
          todayRow({
            plan_items: [
              {
                id: 'item-1',
                item_type: 'rice',
                status: 'filled',
                make_extra: false,
                dishes: { name: 'Sambar Sadam' },
              },
              {
                id: 'item-2',
                item_type: 'poriyal',
                status: 'filled',
                make_extra: false,
                dishes: { name: 'Cabbage Poriyal' },
              },
            ],
          }),
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();
    const slotRow = tree.root.findByProps({ testID: 'slot-row-night' });
    await act(async () => {
      slotRow.props.onPress();
      await flushAsync();
    });

    expect(mockRpc).not.toHaveBeenCalled();
    expect(textOf(tree)).toContain('more than one item');
    expect(tree.root.findByProps({ testID: 'review-day-button' })).toBeTruthy();
  });

  it('opens a calm, inert info sheet from "New ideas" — no scope picker that leads nowhere', async () => {
    mockFrom.mockReturnValue(chainable({ data: [todayRow()], error: null }));

    const tree = await renderScreen();
    const pill = tree.root.findByProps({ testID: 'new-ideas-pill' });
    await act(async () => {
      pill.props.onPress();
    });

    expect(textOf(tree)).toContain(
      'Once the dish list is ready, this will find something new for you.',
    );
  });

  it('falls back to a bare error state when the fetch fails and there is no cache', async () => {
    mockFrom.mockReturnValue(
      chainable({ data: null, error: { message: 'permission denied for table meal_plans' } }),
    );

    const tree = await renderScreen();

    expect(textOf(tree)).toContain("Couldn't load your plan");
  });

  it('renders slot rows in chronological (spine time) order, not the raw DB slot order', async () => {
    const rowFor = (slot: string, dishName: string) => ({
      id: `plan-${slot}`,
      plan_date: today,
      slot,
      is_skipped: false,
      plan_items: [
        {
          id: `item-${slot}`,
          item_type: 'rice',
          status: 'filled',
          make_extra: false,
          dishes: { name: dishName },
        },
      ],
    });

    // Deliberately supplied out of chronological order (and in the DB enum's own order —
    // morning, afternoon, night, snack_1, snack_2, snack_3 — so a regression back to rendering
    // by SLOTS instead of CHRONOLOGICAL_SLOTS would still pass a naively-ordered fixture).
    mockFrom.mockReturnValue(
      chainable({
        data: [
          rowFor('night', 'Night Dish'),
          rowFor('morning', 'Morning Dish'),
          rowFor('snack_2', 'Snack2 Dish'),
          rowFor('afternoon', 'Afternoon Dish'),
          rowFor('snack_1', 'Snack1 Dish'),
          rowFor('snack_3', 'Snack3 Dish'),
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();

    const renderedOrder = [
      ...new Set(
        tree.root
          .findAll(
            (node) =>
              typeof node.type === 'string' &&
              typeof node.props.testID === 'string' &&
              node.props.testID.startsWith('slot-row-'),
          )
          .map((node) => node.props.testID as string),
      ),
    ];

    expect(renderedOrder).toEqual([
      'slot-row-morning',
      'slot-row-snack_1',
      'slot-row-afternoon',
      'slot-row-snack_2',
      'slot-row-night',
      'slot-row-snack_3',
    ]);
  });

  it("never shows user A's cached plan when user B goes offline on the same device", async () => {
    mockUseSession.mockReturnValue({ session: { user: { id: 'user-a' } } });
    mockFrom.mockReturnValue(chainable({ data: [todayRow()], error: null }));

    const userATree = await renderScreen();
    expect(textOf(userATree)).toContain('Sambar Sadam');

    mockUseSession.mockReturnValue({ session: { user: { id: 'user-b' } } });
    mockFrom.mockReturnValue(
      chainable({ data: null, error: { message: 'network request failed' } }),
    );

    const userBTree = await renderScreen();

    expect(textOf(userBTree)).not.toContain('Sambar Sadam');
    expect(textOf(userBTree)).toContain("Couldn't load your plan");
  });

  // MP-061: skip/eating-out toggle — no confirmation dialog, no warning styling.
  it('toggles a slot to skipped in one tap, with no confirmation dialog', async () => {
    const builder = chainable({ data: [todayRow()], error: null });
    mockFrom.mockReturnValue(builder);

    const tree = await renderScreen();
    const slotRow = tree.root.findByProps({ testID: 'slot-row-night' });
    await act(async () => {
      slotRow.props.onPress();
    });

    const toggleButton = tree.root.findByProps({ testID: 'skip-toggle-button' });
    await act(async () => {
      toggleButton.props.onPress();
      await flushAsync();
    });

    expect(builder.update).toHaveBeenCalledWith({ is_skipped: true });
    expect(
      (builder as unknown as { __updateBuilder: { eq: jest.Mock } }).__updateBuilder.eq,
    ).toHaveBeenCalledWith('id', 'plan-1');
    expect(textOf(tree)).toContain('Cooking something of your own');
    expect(textOf(tree)).not.toContain('confirm');
  });

  it('toggles a skipped slot back with neutral copy, not a warning', async () => {
    mockFrom.mockReturnValue(chainable({ data: [todayRow({ is_skipped: true })], error: null }));

    const tree = await renderScreen();
    const slotRow = tree.root.findByProps({ testID: 'slot-row-night' });
    await act(async () => {
      slotRow.props.onPress();
    });

    expect(textOf(tree)).toContain('Actually, cooking this');
  });

  // PR review fix: this screen stays mounted underneath DayReviewEditScreen's route, so an edit
  // made there (swap/add/remove/carry-over) must be visible here on return — not just on the next
  // userId change. Drives the real navigation flow (tap "Review & edit" -> pop back) rather than
  // asserting on the effect internals, so a regression here would mean a stale plan on screen, not
  // just a missing hook call.
  it('refetches the plan when returning from Review & edit, not just on the initial mount', async () => {
    mockFrom.mockReturnValue(
      chainable({
        data: [
          todayRow({
            plan_items: [
              {
                id: 'item-1',
                item_type: 'rice',
                status: 'filled',
                make_extra: false,
                dishes: { name: 'Sambar Sadam' },
              },
              {
                id: 'item-2',
                item_type: 'poriyal',
                status: 'filled',
                make_extra: false,
                dishes: { name: 'Cabbage Poriyal' },
              },
            ],
          }),
        ],
        error: null,
      }),
    );
    let capturedNavigation: { goBack: () => void } | null = null;
    function DummyEditScreen({ navigation }: { navigation: { goBack: () => void } }) {
      capturedNavigation = navigation;
      return null;
    }

    let tree: ReturnType<typeof create>;
    await act(async () => {
      tree = create(
        <NavigationContainer>
          <Stack.Navigator>
            <Stack.Screen name="WeekPlan" component={WeekPlanScreen} />
            <Stack.Screen name="DayReviewEdit" component={DummyEditScreen} />
          </Stack.Navigator>
        </NavigationContainer>,
      );
      await flushAsync();
      await flushAsync();
    });
    expect(mockFrom).toHaveBeenCalledTimes(1);

    const slotRow = tree!.root.findByProps({ testID: 'slot-row-night' });
    await act(async () => {
      slotRow.props.onPress();
      await flushAsync();
    });
    const reviewButton = tree!.root.findByProps({ testID: 'review-day-button' });
    await act(async () => {
      reviewButton.props.onPress();
      await flushAsync();
    });

    expect(capturedNavigation).toBeTruthy();
    await act(async () => {
      capturedNavigation!.goBack();
      await flushAsync();
      await flushAsync();
    });

    expect(mockFrom).toHaveBeenCalledTimes(2);
  });

  // MP-092/093/094: a brand-new user — no meal_plans rows at all, but a generation_jobs row
  // already exists (MP-094's onboarding-trigger claimed it) — must get the honest
  // "building your first plan" state with an instant-fallback preview, not the existing-user
  // StillCookingCard copy that's wrong for a signup whose real first plan may be days out.
  describe('first-plan-pending (MP-092/093/094)', () => {
    function mockFromByTable(generationJobsData: unknown[]) {
      mockFrom.mockImplementation((table: string) =>
        table === 'generation_jobs'
          ? chainable({ data: generationJobsData, error: null })
          : chainable({ data: [], error: null }),
      );
    }

    it('shows the pending state with an instant-fallback preview when a job is pending', async () => {
      mockFromByTable([{ id: 'job-1' }]);
      mockGetInstantFallback.mockResolvedValue([
        { day: today, slot: 'morning', item_type: 'tiffin', dish_id: 'dish-1', dish_name: 'Idli' },
      ]);

      const tree = await renderScreen();

      expect(textOf(tree)).toContain('Building your first plan');
      expect(countByTestId(tree, 'week-plan-first-plan-pending')).toBe(1);
      expect(mockGetInstantFallback).toHaveBeenCalledTimes(1);
    });

    it('still shows the pending card when the instant-fallback fetch fails', async () => {
      mockFromByTable([{ id: 'job-1' }]);
      mockGetInstantFallback.mockRejectedValue(new Error('backend unreachable'));

      const tree = await renderScreen();

      expect(textOf(tree)).toContain('Building your first plan');
    });

    it('stays on the existing still-cooking state when no job is pending', async () => {
      mockFromByTable([]);

      const tree = await renderScreen();

      expect(textOf(tree)).toContain('Putting today together');
      expect(mockGetInstantFallback).not.toHaveBeenCalled();
    });

    it('transitions from the pending state to the real plan when the job completes, via Realtime — not a poll', async () => {
      mockFromByTable([{ id: 'job-1' }]);
      mockGetInstantFallback.mockResolvedValue([]);

      const tree = await renderScreen();
      expect(textOf(tree)).toContain('Building your first plan');
      expect(capturedRealtimeCallback).toBeTruthy();

      // Once the job is 'done', the next fetch finds a real plan — no merge, no flash of both
      // states: the pending UI must be fully replaced, not shown alongside the real one.
      mockFrom.mockReturnValue(chainable({ data: [todayRow()], error: null }));
      await act(async () => {
        capturedRealtimeCallback!({ new: { status: 'done' } });
        await flushAsync();
        await flushAsync();
      });

      expect(textOf(tree)).toContain('Sambar Sadam');
      expect(textOf(tree)).not.toContain('Building your first plan');
    });

    it('does not refetch on a Realtime event for a status other than done', async () => {
      mockFromByTable([{ id: 'job-1' }]);
      mockGetInstantFallback.mockResolvedValue([]);

      await renderScreen();
      const callsBefore = mockFrom.mock.calls.length;

      await act(async () => {
        capturedRealtimeCallback!({ new: { status: 'processing' } });
        await flushAsync();
      });

      expect(mockFrom.mock.calls.length).toBe(callsBefore);
    });

    it('unsubscribes the Realtime channel on unmount', async () => {
      mockFromByTable([]);
      const tree = await renderScreen();

      await act(async () => {
        tree.unmount();
      });

      expect(mockRemoveChannel).toHaveBeenCalledTimes(1);
    });
  });
});
