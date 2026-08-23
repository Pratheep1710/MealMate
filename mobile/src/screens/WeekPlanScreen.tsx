import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

import { supabase } from '../lib/supabase';
import { currentWeekStart, weekDates, SLOTS, type Slot } from '../lib/week';
import type { PlanStackParamList } from '../navigation/types';

// MP-027: renders the signed-in user's weekly plan straight from Supabase, RLS-scoped by
// auth.uid() (0006_rls_policies.sql) — no mocked or local data. A meal_plans row exists per
// (user, plan_date, slot) that's been generated; a slot with no row yet just hasn't been planned.
type PlanItemRow = {
  id: string;
  item_type: string;
  status: 'filled' | 'needs_manual_pick';
  make_extra: boolean;
  dishes: { name: string } | null;
};

type MealPlanRow = {
  id: string;
  plan_date: string;
  slot: Slot;
  is_skipped: boolean;
  plan_items: PlanItemRow[];
};

type PlansBySlot = Map<string, MealPlanRow>; // key: `${plan_date}|${slot}`

function slotKey(planDate: string, slot: string): string {
  return `${planDate}|${slot}`;
}

function slotLabel(slot: Slot): string {
  switch (slot) {
    case 'snack_1':
      return 'Snack 1';
    case 'snack_2':
      return 'Snack 2';
    case 'snack_3':
      return 'Snack 3';
    default:
      return slot.charAt(0).toUpperCase() + slot.slice(1);
  }
}

export function WeekPlanScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<PlanStackParamList, 'WeekPlan'>>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [plansBySlot, setPlansBySlot] = useState<PlansBySlot>(new Map());

  const weekStart = currentWeekStart(new Date());
  const dates = weekDates(weekStart);

  useEffect(() => {
    let ignore = false;

    async function load() {
      setLoading(true);
      setError(null);

      const { data, error: queryError } = await supabase
        .from('meal_plans')
        .select(
          'id, plan_date, slot, is_skipped, plan_items(id, item_type, status, make_extra, dishes(name))',
        )
        .gte('plan_date', dates[0])
        .lte('plan_date', dates[dates.length - 1]);

      if (ignore) {
        return;
      }
      if (queryError) {
        setError(queryError.message);
        setLoading(false);
        return;
      }

      const map: PlansBySlot = new Map();
      for (const row of (data ?? []) as unknown as MealPlanRow[]) {
        map.set(slotKey(row.plan_date, row.slot), row);
      }
      setPlansBySlot(map);
      setLoading(false);
    }

    load();
    return () => {
      ignore = true;
    };
    // dates[0]/dates[dates.length - 1] are derived from `new Date()` at render time, which is
    // stable for the lifetime of this screen instance — re-running on every render would refetch
    // in a loop for no reason.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <View style={styles.centered} testID="week-plan-loading">
        <ActivityIndicator />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error} testID="week-plan-error">
          Couldn&apos;t load this week&apos;s plan: {error}
        </Text>
      </View>
    );
  }

  if (plansBySlot.size === 0) {
    return (
      <View style={styles.centered}>
        <Text style={styles.title}>This week&apos;s plan</Text>
        <Text style={styles.note} testID="week-plan-empty">
          No plan yet for this week.
        </Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.scrollContent} testID="week-plan-scroll">
      {dates.map((date) => (
        <View key={date} style={styles.dayCard} testID={`week-plan-day-${date}`}>
          <View style={styles.dayHeaderRow}>
            <Text style={styles.dayHeader}>{date}</Text>
            <TouchableOpacity
              onPress={() => navigation.navigate('DayReviewEdit', { planDate: date })}
              testID={`week-plan-review-${date}`}
            >
              <Text style={styles.reviewLink}>Review</Text>
            </TouchableOpacity>
          </View>
          {SLOTS.map((slot) => {
            const plan = plansBySlot.get(slotKey(date, slot));
            return (
              <View key={slot} style={styles.slotRow}>
                <Text style={styles.slotLabel}>{slotLabel(slot)}</Text>
                {!plan ? (
                  <Text style={styles.slotValue}>—</Text>
                ) : plan.is_skipped ? (
                  <Text style={styles.slotValue}>Skipped</Text>
                ) : plan.plan_items.length === 0 ? (
                  <Text style={styles.slotValue}>—</Text>
                ) : (
                  <View style={styles.itemList}>
                    {plan.plan_items.map((item) => (
                      <Text key={item.id} style={styles.slotValue}>
                        {item.status === 'needs_manual_pick'
                          ? 'Needs manual pick'
                          : (item.dishes?.name ?? 'Unknown dish')}
                        {item.make_extra ? ' (extra)' : ''}
                      </Text>
                    ))}
                  </View>
                )}
              </View>
            );
          })}
        </View>
      ))}
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
    gap: 16,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
  },
  note: {
    color: '#666',
    textAlign: 'center',
  },
  error: {
    color: '#b00020',
    textAlign: 'center',
  },
  dayCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 12,
    gap: 8,
  },
  dayHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  dayHeader: {
    fontSize: 16,
    fontWeight: '600',
  },
  reviewLink: {
    color: '#2563eb',
  },
  slotRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 8,
  },
  slotLabel: {
    color: '#666',
    width: 90,
  },
  itemList: {
    flex: 1,
    alignItems: 'flex-end',
  },
  slotValue: {
    flex: 1,
    textAlign: 'right',
  },
});
