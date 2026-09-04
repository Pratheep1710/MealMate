import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { act, create } from 'react-test-renderer';

import type { PlanStackParamList } from '../../navigation/types';
import { DayReviewEditScreen } from '../DayReviewEditScreen';

const PLAN_DATE = '2026-08-31';

const mockFrom = jest.fn();
const mockRpc = jest.fn();
const mockUseSession = jest.fn();

jest.mock('../../lib/supabase', () => ({
  supabase: {
    from: (...args: unknown[]) => mockFrom(...args),
    rpc: (...args: unknown[]) => mockRpc(...args),
    auth: { getUser: () => Promise.resolve({ data: { user: { id: 'user-1' } } }) },
  },
}));

jest.mock('../../contexts/SessionContext', () => ({
  useSession: () => mockUseSession(),
}));

function chainable(result: { data: unknown; error: unknown }) {
  const builder: Record<string, unknown> = {};
  for (const method of ['select', 'eq', 'insert', 'delete']) {
    builder[method] = jest.fn(() => builder);
  }
  builder.single = jest.fn(() => Promise.resolve(result));
  builder.then = (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
    Promise.resolve(result).then(resolve, reject);
  return builder;
}

// Mirrors the one shape DayReviewEditScreen.tsx actually calls on an rpc() result: `.single()`.
// The outer object is never awaited directly, only `.single()`'s own return value is.
function rpcResult(result: { data: unknown; error: unknown }) {
  return { single: () => Promise.resolve(result) };
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
          <Stack.Screen
            name="DayReviewEdit"
            component={DayReviewEditScreen}
            initialParams={{ planDate: PLAN_DATE }}
          />
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

function dayPlanFixture() {
  return [
    {
      id: 'plan-1',
      plan_date: PLAN_DATE,
      slot: 'afternoon',
      is_skipped: false,
      plan_items: [
        {
          id: 'item-rice',
          item_type: 'rice',
          status: 'filled',
          make_extra: false,
          dish_id: 'dish-rice',
          dishes: { name: 'Steamed Rice' },
        },
        {
          id: 'item-poriyal',
          item_type: 'poriyal',
          status: 'filled',
          make_extra: false,
          dish_id: 'dish-poriyal',
          dishes: { name: 'Cabbage Poriyal' },
        },
      ],
    },
  ];
}

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSession.mockReturnValue({ session: { user: { id: 'user-1' } } });
  mockRpc.mockReturnValue(Promise.resolve({ data: [], error: null }));
});

describe('DayReviewEditScreen', () => {
  it('renders every plan item for the day, grouped by slot', async () => {
    mockFrom.mockReturnValue(chainable({ data: dayPlanFixture(), error: null }));

    const tree = await renderScreen();

    expect(mockFrom).toHaveBeenCalledWith('meal_plans');
    expect(textOf(tree)).toContain('Steamed Rice');
    expect(textOf(tree)).toContain('Cabbage Poriyal');
  });

  it('loads swap candidates and shows advisory badges without blocking selection', async () => {
    mockFrom.mockReturnValue(chainable({ data: dayPlanFixture(), error: null }));
    mockRpc.mockImplementation((name: string) => {
      if (name === 'list_swap_candidates') {
        return Promise.resolve({
          data: [
            {
              dish_id: 'dish-alt',
              name: 'Lemon Rice',
              veg_or_nonveg: 'veg',
              prep_minutes: 20,
              track_variety: true,
              used_this_week: true,
              used_recently: false,
            },
          ],
          error: null,
        });
      }
      return Promise.resolve({ data: [], error: null });
    });

    const tree = await renderScreen();
    const swapButton = tree.root.findByProps({ testID: 'swap-item-rice' });
    await act(async () => {
      swapButton.props.onPress();
      await flushAsync();
    });

    expect(mockRpc).toHaveBeenCalledWith('list_swap_candidates', {
      target_plan_item_id: 'item-rice',
    });
    expect(textOf(tree)).toContain('Lemon Rice');
    expect(textOf(tree)).toContain('Already used this week');
    // Advisory only — the candidate row itself must still be present/tappable, not disabled.
    expect(tree.root.findByProps({ testID: 'candidate-dish-alt' })).toBeTruthy();
  });

  it('applies a swap via the RPC and updates the item locally', async () => {
    mockFrom.mockReturnValue(chainable({ data: dayPlanFixture(), error: null }));
    mockRpc.mockImplementation((name: string) => {
      if (name === 'list_swap_candidates') {
        return Promise.resolve({
          data: [
            {
              dish_id: 'dish-alt',
              name: 'Lemon Rice',
              veg_or_nonveg: 'veg',
              prep_minutes: 20,
              track_variety: true,
              used_this_week: false,
              used_recently: false,
            },
          ],
          error: null,
        });
      }
      if (name === 'swap_plan_item') {
        return rpcResult({
          data: {
            id: 'item-rice',
            plan_id: 'plan-1',
            item_type: 'rice',
            dish_id: 'dish-alt',
            status: 'filled',
            make_extra: false,
          },
          error: null,
        });
      }
      return Promise.resolve({ data: [], error: null });
    });

    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'swap-item-rice' }).props.onPress();
      await flushAsync();
    });
    await act(async () => {
      tree.root.findByProps({ testID: 'candidate-dish-alt' }).props.onPress();
      await flushAsync();
    });

    expect(mockRpc).toHaveBeenCalledWith('swap_plan_item', {
      target_plan_item_id: 'item-rice',
      new_dish_id: 'dish-alt',
    });
    expect(textOf(tree)).toContain('Lemon Rice');
    expect(textOf(tree)).not.toContain('Steamed Rice');
  });

  it('removes an item via the RPC, optimistically and reverting on failure', async () => {
    mockFrom.mockReturnValue(chainable({ data: dayPlanFixture(), error: null }));
    mockRpc.mockImplementation((name: string) => {
      if (name === 'remove_plan_item') {
        return Promise.resolve({ data: null, error: { message: 'not found or not owned' } });
      }
      return Promise.resolve({ data: [], error: null });
    });

    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'remove-item-poriyal' }).props.onPress();
      await flushAsync();
    });

    expect(mockRpc).toHaveBeenCalledWith('remove_plan_item', {
      target_plan_item_id: 'item-poriyal',
    });
    // The RPC rejected the remove — the optimistic removal must be reverted, not left applied.
    expect(textOf(tree)).toContain('Cabbage Poriyal');
  });

  it('dismisses an advisory badge without blocking the underlying swap', async () => {
    // MP-062 PR review fix: the badge itself must be dismissible, and dismissing it must not
    // touch the candidate row's own tappability.
    mockFrom.mockReturnValue(chainable({ data: dayPlanFixture(), error: null }));
    mockRpc.mockImplementation((name: string) => {
      if (name === 'list_swap_candidates') {
        return Promise.resolve({
          data: [
            {
              dish_id: 'dish-alt',
              name: 'Lemon Rice',
              veg_or_nonveg: 'veg',
              prep_minutes: 20,
              track_variety: true,
              used_this_week: true,
              used_recently: false,
              exceeds_nonveg_quota: false,
            },
          ],
          error: null,
        });
      }
      if (name === 'swap_plan_item') {
        return rpcResult({
          data: {
            id: 'item-rice',
            plan_id: 'plan-1',
            item_type: 'rice',
            dish_id: 'dish-alt',
            status: 'filled',
            make_extra: false,
          },
          error: null,
        });
      }
      return Promise.resolve({ data: [], error: null });
    });

    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'swap-item-rice' }).props.onPress();
      await flushAsync();
    });
    expect(textOf(tree)).toContain('Already used this week');

    await act(async () => {
      tree.root.findByProps({ testID: 'dismiss-badges-dish-alt' }).props.onPress();
    });
    expect(textOf(tree)).not.toContain('Already used this week');

    // Still tappable after the badge is dismissed.
    await act(async () => {
      tree.root.findByProps({ testID: 'candidate-dish-alt' }).props.onPress();
      await flushAsync();
    });
    expect(mockRpc).toHaveBeenCalledWith('swap_plan_item', {
      target_plan_item_id: 'item-rice',
      new_dish_id: 'dish-alt',
    });
  });

  it('flags a swap candidate that would exceed the non-veg quota, advisory only', async () => {
    mockFrom.mockReturnValue(chainable({ data: dayPlanFixture(), error: null }));
    mockRpc.mockImplementation((name: string) => {
      if (name === 'list_swap_candidates') {
        return Promise.resolve({
          data: [
            {
              dish_id: 'dish-alt',
              name: 'Chicken Rice',
              veg_or_nonveg: 'nonveg',
              prep_minutes: 20,
              track_variety: true,
              used_this_week: false,
              used_recently: false,
              exceeds_nonveg_quota: true,
            },
          ],
          error: null,
        });
      }
      return Promise.resolve({ data: [], error: null });
    });

    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'swap-item-rice' }).props.onPress();
      await flushAsync();
    });

    expect(textOf(tree)).toContain('Over your non-veg quota this week');
    expect(tree.root.findByProps({ testID: 'candidate-dish-alt' })).toBeTruthy();
  });

  it('only offers item types the slot is missing from the add sheet', async () => {
    // MP-060 PR review fix: this slot already has rice and poriyal — the picker must not offer
    // either again (add_plan_item_to_slot itself now rejects a duplicate type too).
    mockFrom.mockReturnValue(chainable({ data: dayPlanFixture(), error: null }));

    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'add-item-afternoon' }).props.onPress();
    });

    expect(() => tree.root.findByProps({ testID: 'item-type-rice' })).toThrow();
    expect(() => tree.root.findByProps({ testID: 'item-type-poriyal' })).toThrow();
    expect(tree.root.findByProps({ testID: 'item-type-gravy' })).toBeTruthy();
  });

  it('carries an item into the derived next slot, not an open choice of slots', async () => {
    // MP-064 PR review fix: only the immediate next chronological slot is offered, computed by
    // the screen itself — carry_over_plan_item's own next-slot check is the second line of
    // defense, not the only one.
    const plans = [
      dayPlanFixture()[0],
      {
        id: 'plan-2',
        plan_date: PLAN_DATE,
        slot: 'snack_2',
        is_skipped: false,
        plan_items: [],
      },
    ];
    mockFrom.mockReturnValue(chainable({ data: plans, error: null }));
    mockRpc.mockImplementation((name: string) => {
      if (name === 'carry_over_plan_item') {
        return rpcResult({
          data: {
            id: 'item-carried',
            plan_id: 'plan-2',
            item_type: 'rice',
            dish_id: 'dish-rice',
            status: 'filled',
            make_extra: true,
          },
          error: null,
        });
      }
      return Promise.resolve({ data: [], error: null });
    });

    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'extra-item-rice' }).props.onPress();
    });

    // "Carry into " and "Evening" (snack_2's SLOT_META label) render as separate Text children,
    // so textOf's JSON dump keeps them as adjacent array entries rather than one concatenated
    // string — assert on the always-present label text plus the button itself, not the join.
    expect(textOf(tree)).toContain('Evening');
    expect(tree.root.findByProps({ testID: 'carry-target-next-slot' })).toBeTruthy();
    await act(async () => {
      tree.root.findByProps({ testID: 'carry-target-next-slot' }).props.onPress();
      await flushAsync();
    });

    expect(mockRpc).toHaveBeenCalledWith('carry_over_plan_item', {
      source_plan_item_id: 'item-rice',
      target_plan_id: 'plan-2',
    });
  });

  it('tells the user there is no later slot today rather than offering nowhere to carry to', async () => {
    const plans = [
      {
        id: 'plan-night',
        plan_date: PLAN_DATE,
        slot: 'night',
        is_skipped: false,
        plan_items: [
          {
            id: 'item-night-gravy',
            item_type: 'gravy',
            status: 'filled',
            make_extra: false,
            dish_id: 'dish-gravy',
            dishes: { name: 'Sambar' },
          },
        ],
      },
    ];
    mockFrom.mockReturnValue(chainable({ data: plans, error: null }));

    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'extra-item-night-gravy' }).props.onPress();
    });

    expect(textOf(tree)).toContain('No later slot today to carry this into.');
    expect(() => tree.root.findByProps({ testID: 'carry-target-next-slot' })).toThrow();
  });

  it('toggles a favorite star from the swap candidate list without blocking the swap', async () => {
    mockFrom.mockImplementation((table: string) => {
      if (table === 'user_favorite_dishes') {
        return chainable({ data: [], error: null });
      }
      return chainable({ data: dayPlanFixture(), error: null });
    });
    mockRpc.mockImplementation((name: string) => {
      if (name === 'list_swap_candidates') {
        return Promise.resolve({
          data: [
            {
              dish_id: 'dish-alt',
              name: 'Lemon Rice',
              veg_or_nonveg: 'veg',
              prep_minutes: 20,
              track_variety: true,
              used_this_week: false,
              used_recently: false,
            },
          ],
          error: null,
        });
      }
      return Promise.resolve({ data: [], error: null });
    });

    const tree = await renderScreen();
    await act(async () => {
      tree.root.findByProps({ testID: 'swap-item-rice' }).props.onPress();
      await flushAsync();
    });
    await act(async () => {
      tree.root.findByProps({ testID: 'favorite-dish-alt' }).props.onPress();
      await flushAsync();
    });

    expect(mockFrom).toHaveBeenCalledWith('user_favorite_dishes');
    // Toggling favorite must not have applied the swap.
    expect(textOf(tree)).toContain('Steamed Rice');
  });
});
