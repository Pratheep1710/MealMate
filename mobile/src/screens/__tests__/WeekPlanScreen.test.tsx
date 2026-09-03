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

jest.mock('../../lib/supabase', () => ({
  supabase: {
    from: (...args: unknown[]) => mockFrom(...args),
    rpc: (...args: unknown[]) => mockRpc(...args),
  },
}));

jest.mock('../../contexts/SessionContext', () => ({
  useSession: () => mockUseSession(),
}));

function chainable(
  result: { data: unknown; error: unknown },
  updateResult: { error: unknown } = { error: null },
) {
  const builder: Record<string, unknown> = {};
  for (const method of ['select', 'gte', 'lte', 'eq', 'in', 'order']) {
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
  mockUseSession.mockReturnValue({ session: { user: { id: 'user-1' } } });
  mockRpc.mockReturnValue(Promise.resolve({ data: [], error: null }));
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
});
