import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { supabase } from '../lib/supabase';
import { currentWeekStart, weekDates } from '../lib/week';

// MP-028: renders the frozen grocery_list_snapshot for the current week (RLS-scoped, real data —
// 0006_rls_policies.sql / 0005_availability_grocery_snapshot_schema.sql) plus a "newly introduced"
// delta section. Per the Decisions Risks tab, the snapshot is frozen at week-ready and never
// rewritten by later edits — so ingredients required by the *current* plan but absent from the
// frozen snapshot are shown as a separately badged addition, not merged into (or replacing) the
// frozen list itself.
type SnapshotIngredient = { ingredient_id: string; name: string };

type PlanItemDishIdRow = {
  plan_items: { dish_id: string | null }[];
};

type DishIngredientRow = {
  ingredient_id: string;
  ingredients: { canonical_name: string } | null;
};

// Supabase errors (PostgrestError) are plain objects with a `.message` string, not Error
// instances, so `err instanceof Error` alone would miss them and fall through to "[object Object]".
function errorMessage(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  if (
    typeof err === 'object' &&
    err !== null &&
    typeof (err as { message?: unknown }).message === 'string'
  ) {
    return (err as { message: string }).message;
  }
  return String(err);
}

async function fetchCurrentWeekDishIds(dates: string[]): Promise<string[]> {
  const { data, error } = await supabase
    .from('meal_plans')
    .select('plan_items(dish_id)')
    .gte('plan_date', dates[0])
    .lte('plan_date', dates[dates.length - 1]);

  if (error) {
    throw error;
  }

  const dishIds = new Set<string>();
  for (const row of (data ?? []) as unknown as PlanItemDishIdRow[]) {
    for (const item of row.plan_items) {
      if (item.dish_id) {
        dishIds.add(item.dish_id);
      }
    }
  }
  return [...dishIds];
}

async function fetchCurrentlyRequiredIngredients(dishIds: string[]): Promise<Map<string, string>> {
  if (dishIds.length === 0) {
    return new Map();
  }
  const { data, error } = await supabase
    .from('dish_ingredients')
    .select('ingredient_id, ingredients(canonical_name)')
    .in('dish_id', dishIds);

  if (error) {
    throw error;
  }

  const byId = new Map<string, string>();
  for (const row of (data ?? []) as unknown as DishIngredientRow[]) {
    byId.set(row.ingredient_id, row.ingredients?.canonical_name ?? row.ingredient_id);
  }
  return byId;
}

export function GroceryListScreen() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [frozenList, setFrozenList] = useState<SnapshotIngredient[] | null>(null);
  const [addedSinceSnapshot, setAddedSinceSnapshot] = useState<SnapshotIngredient[]>([]);

  useEffect(() => {
    let ignore = false;

    async function load() {
      setLoading(true);
      setError(null);

      const weekStart = currentWeekStart(new Date());
      const dates = weekDates(weekStart);

      try {
        const { data: snapshot, error: snapshotError } = await supabase
          .from('grocery_list_snapshot')
          .select('week_start, ingredients')
          .eq('week_start', dates[0])
          .maybeSingle();

        if (snapshotError) {
          throw snapshotError;
        }
        if (ignore) {
          return;
        }

        const frozenIngredients = ((snapshot?.ingredients ?? []) as SnapshotIngredient[]) || [];
        setFrozenList(snapshot ? frozenIngredients : null);

        if (snapshot) {
          const frozenIds = new Set(frozenIngredients.map((i) => i.ingredient_id));
          const dishIds = await fetchCurrentWeekDishIds(dates);
          const currentlyRequired = await fetchCurrentlyRequiredIngredients(dishIds);
          if (ignore) {
            return;
          }
          const added: SnapshotIngredient[] = [];
          for (const [ingredientId, name] of currentlyRequired) {
            if (!frozenIds.has(ingredientId)) {
              added.push({ ingredient_id: ingredientId, name });
            }
          }
          setAddedSinceSnapshot(added);
        }

        setLoading(false);
      } catch (err) {
        if (!ignore) {
          setError(errorMessage(err));
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      ignore = true;
    };
  }, []);

  if (loading) {
    return (
      <View style={styles.centered} testID="grocery-list-loading">
        <ActivityIndicator />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error} testID="grocery-list-error">
          Couldn&apos;t load the grocery list: {error}
        </Text>
      </View>
    );
  }

  if (frozenList === null) {
    return (
      <View style={styles.centered}>
        <Text style={styles.title}>Grocery list</Text>
        <Text style={styles.note} testID="grocery-list-empty">
          Your list isn&apos;t ready yet — it freezes once this week&apos;s plan is generated.
        </Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.scrollContent} testID="grocery-list-scroll">
      <Text style={styles.title}>Grocery list</Text>
      {frozenList.length === 0 ? (
        <Text style={styles.note}>Nothing on this week&apos;s list.</Text>
      ) : (
        frozenList.map((ingredient) => (
          <View key={ingredient.ingredient_id} style={styles.row} testID="grocery-item-frozen">
            <Text style={styles.itemName}>{ingredient.name}</Text>
          </View>
        ))
      )}

      {addedSinceSnapshot.length > 0 ? (
        <View style={styles.addedSection}>
          <Text style={styles.sectionHeader}>Added since your list was made</Text>
          {addedSinceSnapshot.map((ingredient) => (
            <View key={ingredient.ingredient_id} style={styles.row} testID="grocery-item-added">
              <Text style={styles.itemName}>{ingredient.name}</Text>
              <Text style={styles.badge}>New</Text>
            </View>
          ))}
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    gap: 12,
  },
  scrollContent: {
    padding: 16,
    gap: 8,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 8,
  },
  note: {
    color: '#666',
    textAlign: 'center',
  },
  error: {
    color: '#b00020',
    textAlign: 'center',
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#eee',
  },
  itemName: {
    fontSize: 15,
  },
  addedSection: {
    marginTop: 16,
    gap: 4,
  },
  sectionHeader: {
    fontSize: 13,
    fontWeight: '600',
    color: '#666',
    marginBottom: 4,
  },
  badge: {
    backgroundColor: '#dbeafe',
    color: '#1d4ed8',
    fontSize: 11,
    fontWeight: '600',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: 'hidden',
  },
});
