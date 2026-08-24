import { act, create } from 'react-test-renderer';

import { GroceryListScreen } from '../GroceryListScreen';

const mockFrom = jest.fn();

jest.mock('../../lib/supabase', () => ({
  supabase: { from: (...args: unknown[]) => mockFrom(...args) },
}));

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

function mockTables(tables: Record<string, { data: unknown; error: unknown }>) {
  mockFrom.mockImplementation((table: string) => chainable(tables[table]));
}

// GroceryListScreen chains up to three sequential `await`s (snapshot, then dish ids, then
// dish ingredients) before settling. A single microtask flush isn't reliably enough hops to drain
// all of them; a macrotask (setTimeout) boundary only fires after every currently-queued
// microtask has run, however many chained `.then()`s are pending, so it flushes deterministically
// regardless of how many awaits are chained.
function flushAsync(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function renderScreen() {
  let tree: ReturnType<typeof create>;
  await act(async () => {
    tree = create(<GroceryListScreen />);
    await flushAsync();
    await flushAsync();
  });
  return tree!;
}

function textOf(tree: ReturnType<typeof create>): string {
  return JSON.stringify(tree.toJSON());
}

function countHostNodesWithTestId(tree: ReturnType<typeof create>, testId: string): number {
  return tree.root.findAll((node) => typeof node.type === 'string' && node.props.testID === testId)
    .length;
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('GroceryListScreen', () => {
  it('renders the frozen snapshot list from a real RLS-scoped read', async () => {
    mockTables({
      grocery_list_snapshot: {
        data: {
          week_start: '2026-08-24',
          ingredients: [{ ingredient_id: 'ing-1', name: 'Onion' }],
        },
        error: null,
      },
      meal_plans: { data: [], error: null },
      dish_ingredients: { data: [], error: null },
    });

    const tree = await renderScreen();

    expect(mockFrom).toHaveBeenCalledWith('grocery_list_snapshot');
    expect(textOf(tree)).toContain('Onion');
  });

  it('badges an ingredient required by the current plan but absent from the frozen snapshot', async () => {
    mockTables({
      grocery_list_snapshot: {
        data: {
          week_start: '2026-08-24',
          ingredients: [{ ingredient_id: 'ing-1', name: 'Onion' }],
        },
        error: null,
      },
      meal_plans: { data: [{ plan_items: [{ dish_id: 'dish-2' }] }], error: null },
      dish_ingredients: {
        data: [{ ingredient_id: 'ing-2', ingredients: { canonical_name: 'Carrot' } }],
        error: null,
      },
    });

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('Carrot');
    expect(textOf(tree)).toContain('New');
    // The frozen list itself is untouched — Onion has no badge. findAllByProps would also match
    // the composite View wrapping each host node (double-counting), so filter to host nodes only.
    const addedNodes = countHostNodesWithTestId(tree, 'grocery-item-added');
    expect(addedNodes).toBe(1);
  });

  it('does not badge an ingredient that is already in the frozen snapshot', async () => {
    mockTables({
      grocery_list_snapshot: {
        data: {
          week_start: '2026-08-24',
          ingredients: [{ ingredient_id: 'ing-1', name: 'Onion' }],
        },
        error: null,
      },
      meal_plans: { data: [{ plan_items: [{ dish_id: 'dish-1' }] }], error: null },
      dish_ingredients: {
        data: [{ ingredient_id: 'ing-1', ingredients: { canonical_name: 'Onion' } }],
        error: null,
      },
    });

    const tree = await renderScreen();

    expect(countHostNodesWithTestId(tree, 'grocery-item-added')).toBe(0);
  });

  it('shows a not-ready state when no snapshot has been frozen yet', async () => {
    mockTables({
      grocery_list_snapshot: { data: null, error: null },
      meal_plans: { data: [], error: null },
      dish_ingredients: { data: [], error: null },
    });

    const tree = await renderScreen();

    expect(textOf(tree)).toContain("isn't ready yet");
  });

  it('excludes skipped meal plans from the "currently required" query, so a skipped meal never produces a false "New" badge', async () => {
    const mealPlansBuilder = chainable({
      data: [{ plan_items: [{ dish_id: 'dish-2' }] }],
      error: null,
    });
    mockFrom.mockImplementation((table: string) => {
      if (table === 'meal_plans') {
        return mealPlansBuilder;
      }
      const tables: Record<string, { data: unknown; error: unknown }> = {
        grocery_list_snapshot: {
          data: {
            week_start: '2026-08-24',
            ingredients: [{ ingredient_id: 'ing-1', name: 'Onion' }],
          },
          error: null,
        },
        dish_ingredients: {
          data: [{ ingredient_id: 'ing-2', ingredients: { canonical_name: 'Carrot' } }],
          error: null,
        },
      };
      return chainable(tables[table]);
    });

    await renderScreen();

    // The bug this guards: an eating-out/skipped meal isn't cooked, so its ingredients must not
    // be treated as "currently required" — without filtering at the query, a skipped meal that
    // used a not-yet-frozen ingredient would badge it as "New" even though it will never be bought.
    expect(mealPlansBuilder.eq).toHaveBeenCalledWith('is_skipped', false);
  });

  it('surfaces a query error instead of silently showing an empty list', async () => {
    mockTables({
      grocery_list_snapshot: {
        data: null,
        error: { message: 'permission denied for table grocery_list_snapshot' },
      },
      meal_plans: { data: [], error: null },
      dish_ingredients: { data: [], error: null },
    });

    const tree = await renderScreen();

    expect(textOf(tree)).toContain('permission denied for table grocery_list_snapshot');
  });
});
