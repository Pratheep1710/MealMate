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

jest.mock('../../lib/supabase', () => ({
  supabase: { from: (...args: unknown[]) => mockFrom(...args) },
}));

function chainable(result: { data: unknown; error: unknown }) {
  const builder: Record<string, unknown> = {};
  for (const method of ['select', 'gte', 'lte', 'eq', 'in', 'order']) {
    builder[method] = jest.fn(() => builder);
  }
  builder.then = (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
    Promise.resolve(result).then(resolve, reject);
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

  it('opens a calm, inert detail sheet when a slot is tapped — no fake edit options', async () => {
    mockFrom.mockReturnValue(chainable({ data: [todayRow()], error: null }));

    const tree = await renderScreen();
    const slotRow = tree.root.findByProps({ testID: 'slot-row-night' });
    await act(async () => {
      slotRow.props.onPress();
    });

    expect(textOf(tree)).toContain('Swapping opens up once the dish list is ready.');
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
});
