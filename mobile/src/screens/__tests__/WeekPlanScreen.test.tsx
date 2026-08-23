import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { act, create } from 'react-test-renderer';

import { currentWeekStart, weekDates } from '../../lib/week';
import type { PlanStackParamList } from '../../navigation/types';
import { WeekPlanScreen } from '../WeekPlanScreen';

const dates = weekDates(currentWeekStart(new Date()));
const monday = dates[0];

const mockFrom = jest.fn();
const mockNavigate = jest.fn();

jest.mock('../../lib/supabase', () => ({
  supabase: { from: (...args: unknown[]) => mockFrom(...args) },
}));

jest.mock('@react-navigation/native', () => {
  const actual = jest.requireActual('@react-navigation/native');
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

function chainable(result: { data: unknown; error: unknown }) {
  const builder: Record<string, unknown> = {};
  for (const method of ['select', 'gte', 'lte', 'eq', 'in', 'order']) {
    builder[method] = jest.fn(() => builder);
  }
  builder.maybeSingle = jest.fn(() => Promise.resolve(result));
  builder.then = (resolve: (value: unknown) => unknown, reject?: (reason: unknown) => unknown) =>
    Promise.resolve(result).then(resolve, reject);
  return builder;
}

const Stack = createNativeStackNavigator<PlanStackParamList>();

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
  });
  return tree!;
}

function textOf(tree: ReturnType<typeof create>): string {
  return JSON.stringify(tree.toJSON());
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('WeekPlanScreen', () => {
  it('renders a filled slot with the dish name from a real RLS-scoped read', async () => {
    mockFrom.mockReturnValue(
      chainable({
        data: [
          {
            id: 'plan-1',
            plan_date: monday,
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
          },
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();

    expect(mockFrom).toHaveBeenCalledWith('meal_plans');
    expect(textOf(tree)).toContain('Sambar Sadam');
  });

  it('shows "Needs manual pick" for a needs_manual_pick item instead of a blank slot', async () => {
    mockFrom.mockReturnValue(
      chainable({
        data: [
          {
            id: 'plan-1',
            plan_date: monday,
            slot: 'night',
            is_skipped: false,
            plan_items: [
              {
                id: 'item-1',
                item_type: 'rice',
                status: 'needs_manual_pick',
                make_extra: false,
                dishes: null,
              },
            ],
          },
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('Needs manual pick');
  });

  it('shows Skipped for a day marked is_skipped', async () => {
    mockFrom.mockReturnValue(
      chainable({
        data: [
          { id: 'plan-1', plan_date: monday, slot: 'night', is_skipped: true, plan_items: [] },
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('Skipped');
  });

  it('shows an empty state when the week has no plan yet, not a broken grid', async () => {
    mockFrom.mockReturnValue(chainable({ data: [], error: null }));

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('No plan yet for this week');
  });

  it('surfaces a query error instead of silently showing an empty week', async () => {
    mockFrom.mockReturnValue(
      chainable({ data: null, error: { message: 'permission denied for table meal_plans' } }),
    );

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('permission denied for table meal_plans');
  });

  it("navigates to DayReviewEdit with the pressed day's date", async () => {
    mockFrom.mockReturnValue(
      chainable({
        data: [
          {
            id: 'plan-1',
            plan_date: monday,
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
          },
        ],
        error: null,
      }),
    );

    const tree = await renderScreen();
    const reviewButton = tree.root.findByProps({ testID: `week-plan-review-${monday}` });
    await act(async () => {
      reviewButton.props.onPress();
    });

    expect(mockNavigate).toHaveBeenCalledWith('DayReviewEdit', { planDate: monday });
  });
});
