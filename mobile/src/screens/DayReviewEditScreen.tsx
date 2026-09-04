import { useRoute, type RouteProp } from '@react-navigation/native';
import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { BottomSheet } from '../components/BottomSheet';
import { useSession } from '../contexts/SessionContext';
import { addFavorite, listFavorites, removeFavorite } from '../lib/favorites';
import { supabase } from '../lib/supabase';
import type { PlanStackParamList } from '../navigation/types';
import { colors, fonts, radii, spacing } from '../theme/tokens';
import { CHRONOLOGICAL_SLOTS, SLOT_META, type Slot } from './weekPlan/rollingDays';

// MP-058/059/060/062/064 — item-level swap/add/remove, the "later phase" this screen's stub used
// to defer to. Swap/add both call a Postgres RPC (supabase/migrations/0019_plan_item_edit_rpcs.sql)
// rather than a raw client write, because the write needs validation RLS alone can't express — item
// type must match the slot's requirement, and the dish must not conflict with the user's dietary
// restrictions (the same hard gate app/services/generation_eligibility.py enforces for generation
// and fallback, reimplemented in SQL since that Python module never runs behind a live request the
// client could reach). Recent/in-week-use badges (MP-062) are advisory only — see their own note
// below for why nothing here ever blocks a save on them.

type ItemType = 'tiffin' | 'rice' | 'gravy' | 'poriyal' | 'kootu' | 'curd' | 'snack' | 'sweet';
const ADDABLE_ITEM_TYPES: ItemType[] = [
  'tiffin',
  'rice',
  'gravy',
  'poriyal',
  'kootu',
  'curd',
  'snack',
  'sweet',
];

type PlanItemRow = {
  id: string;
  item_type: string;
  status: 'filled' | 'needs_manual_pick';
  make_extra: boolean;
  dish_id: string | null;
  dishes: { name: string } | null;
};

type MealPlanRow = {
  id: string;
  plan_date: string;
  slot: Slot;
  is_skipped: boolean;
  plan_items: PlanItemRow[];
};

type SwapCandidate = {
  dish_id: string;
  name: string;
  veg_or_nonveg: string;
  prep_minutes: number | null;
  track_variety: boolean;
  used_this_week: boolean;
  used_recently: boolean;
  exceeds_nonveg_quota: boolean;
};

type DishOption = { id: string; name: string; veg_or_nonveg: string; dietary_flags: string[] };

type ViewState = { kind: 'loading' } | { kind: 'error' } | { kind: 'ready'; plans: MealPlanRow[] };

type SwapSheetState = { planItemId: string; itemType: string } | null;
type AddSheetState = { planId: string; slot: Slot; existingItemTypes: string[] } | null;
type CarrySheetState = {
  sourcePlanItemId: string;
  itemType: string;
  targetPlanId: string | null;
  targetSlotLabel: string | null;
} | null;

async function fetchDayPlan(planDate: string): Promise<MealPlanRow[]> {
  const { data, error } = await supabase
    .from('meal_plans')
    .select(
      'id, plan_date, slot, is_skipped, plan_items(id, item_type, status, make_extra, dish_id, dishes(name))',
    )
    .eq('plan_date', planDate);
  if (error) {
    throw error;
  }
  return (data ?? []) as unknown as MealPlanRow[];
}

export function DayReviewEditScreen() {
  const { params } = useRoute<RouteProp<PlanStackParamList, 'DayReviewEdit'>>();
  const { planDate } = params;

  const { session } = useSession();
  const userId = session?.user.id ?? null;

  const [view, setView] = useState<ViewState>({ kind: 'loading' });
  const [swapSheet, setSwapSheet] = useState<SwapSheetState>(null);
  const [addSheet, setAddSheet] = useState<AddSheetState>(null);
  const [carrySheet, setCarrySheet] = useState<CarrySheetState>(null);
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());

  const load = async () => {
    setView({ kind: 'loading' });
    try {
      const plans = await fetchDayPlan(planDate);
      setView({ kind: 'ready', plans });
    } catch {
      setView({ kind: 'error' });
    }
  };

  useEffect(() => {
    if (!userId) {
      return;
    }
    listFavorites(userId)
      .then((favorites) => setFavoriteIds(new Set(favorites.map((favorite) => favorite.dish_id))))
      .catch(() => {
        // A favorites-load failure just means no star shows as filled yet — not worth an error
        // state of its own on a screen whose primary job is the plan itself.
      });
  }, [userId]);

  // MP-063: toggled from wherever a dish is actually being looked at (the swap/add pickers below)
  // rather than a separate management flow — optimistic like every other edit on this screen, with
  // the cap's rejection (surfaced by the DB trigger, 0018_favorites_cap.sql) reverting the star.
  const toggleFavorite = async (dishId: string) => {
    if (!userId) {
      return;
    }
    const wasFavorite = favoriteIds.has(dishId);
    setFavoriteIds((current) => {
      const next = new Set(current);
      if (wasFavorite) {
        next.delete(dishId);
      } else {
        next.add(dishId);
      }
      return next;
    });
    if (wasFavorite) {
      await removeFavorite(userId, dishId);
      return;
    }
    const { capReached } = await addFavorite(userId, dishId);
    if (capReached) {
      setFavoriteIds((current) => {
        const next = new Set(current);
        next.delete(dishId);
        return next;
      });
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planDate]);

  const replaceItem = (updated: PlanItemRow) => {
    if (view.kind !== 'ready') {
      return;
    }
    setView({
      kind: 'ready',
      plans: view.plans.map((plan) => ({
        ...plan,
        plan_items: plan.plan_items.map((item) => (item.id === updated.id ? updated : item)),
      })),
    });
  };

  const addItemLocally = (planId: string, item: PlanItemRow) => {
    if (view.kind !== 'ready') {
      return;
    }
    setView({
      kind: 'ready',
      plans: view.plans.map((plan) =>
        plan.id === planId ? { ...plan, plan_items: [...plan.plan_items, item] } : plan,
      ),
    });
  };

  const removeItemLocally = (planItemId: string) => {
    if (view.kind !== 'ready') {
      return;
    }
    setView({
      kind: 'ready',
      plans: view.plans.map((plan) => ({
        ...plan,
        plan_items: plan.plan_items.filter((item) => item.id !== planItemId),
      })),
    });
  };

  const handleSwap = async (planItemId: string, dishId: string, dishName: string) => {
    setBusyItemId(planItemId);
    setSwapSheet(null);
    const { data, error } = await supabase
      .rpc('swap_plan_item', { target_plan_item_id: planItemId, new_dish_id: dishId })
      .single();
    setBusyItemId(null);
    if (error || !data) {
      // The RPC's own error already covers "why" (item_type mismatch, dietary conflict, not
      // owned) — nothing to correct locally since the optimistic view was never mutated.
      return;
    }
    const row = data as PlanItemRow;
    replaceItem({ ...row, dishes: { name: dishName } });
  };

  const handleAdd = async (planId: string, itemType: ItemType, dish: DishOption) => {
    setAddSheet(null);
    const { data, error } = await supabase
      .rpc('add_plan_item_to_slot', {
        target_plan_id: planId,
        new_item_type: itemType,
        new_dish_id: dish.id,
      })
      .single();
    if (error || !data) {
      return;
    }
    const row = data as PlanItemRow;
    addItemLocally(planId, { ...row, dishes: { name: dish.name } });
  };

  const handleRemove = async (planItemId: string) => {
    setBusyItemId(planItemId);
    const previous = view.kind === 'ready' ? view.plans : null;
    removeItemLocally(planItemId);
    const { error } = await supabase.rpc('remove_plan_item', { target_plan_item_id: planItemId });
    setBusyItemId(null);
    if (error && previous) {
      setView({ kind: 'ready', plans: previous });
    }
  };

  const handleCarryOver = async (sourcePlanItemId: string, targetPlanId: string) => {
    setCarrySheet(null);
    if (view.kind !== 'ready') {
      return;
    }
    const source = view.plans
      .flatMap((plan) => plan.plan_items)
      .find((item) => item.id === sourcePlanItemId);
    const { data, error } = await supabase
      .rpc('carry_over_plan_item', {
        source_plan_item_id: sourcePlanItemId,
        target_plan_id: targetPlanId,
      })
      .single();
    if (error || !data || !source) {
      return;
    }
    const row = data as PlanItemRow;
    addItemLocally(targetPlanId, { ...row, dishes: source.dishes });
  };

  if (view.kind === 'loading') {
    return (
      <View style={styles.centered} testID="day-review-loading">
        <Text style={styles.infoBody}>Loading…</Text>
      </View>
    );
  }

  if (view.kind === 'error') {
    return (
      <View style={styles.centered} testID="day-review-error">
        <Text style={styles.infoTitle}>Couldn&apos;t load this day</Text>
        <TouchableOpacity style={styles.primaryButton} onPress={load}>
          <Text style={styles.primaryButtonLabel}>Try again</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const slotsForToday = CHRONOLOGICAL_SLOTS.map(
    (slot) => view.plans.find((plan) => plan.slot === slot) ?? null,
  );

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll} testID="day-review-ready">
        {slotsForToday.map((plan, index) => {
          const slot = CHRONOLOGICAL_SLOTS[index];
          const meta = SLOT_META[slot];
          if (!plan) {
            return null;
          }
          return (
            <View key={slot} style={styles.slotCard}>
              <Text style={styles.slotHeading}>
                {meta.label} · {meta.time}
              </Text>
              {plan.plan_items.map((item) => {
                // PR review fix (MP-064): make-extra only ever carries into the very next
                // chronological slot of the same day (functional spec §6.3's own example — lunch
                // reused for dinner) — the RPC now enforces this too, but deriving the one valid
                // target here means the sheet never offers a choice that would just be rejected.
                const nextSlot = CHRONOLOGICAL_SLOTS[index + 1] ?? null;
                const nextPlan = nextSlot ? (slotsForToday[index + 1] ?? null) : null;
                return (
                  <PlanItemRowView
                    key={item.id}
                    item={item}
                    busy={busyItemId === item.id}
                    onSwap={() => setSwapSheet({ planItemId: item.id, itemType: item.item_type })}
                    onRemove={() => handleRemove(item.id)}
                    onMakeExtra={
                      item.status === 'filled'
                        ? () =>
                            setCarrySheet({
                              sourcePlanItemId: item.id,
                              itemType: item.item_type,
                              targetPlanId: nextPlan ? nextPlan.id : null,
                              targetSlotLabel: nextSlot ? SLOT_META[nextSlot].label : null,
                            })
                        : undefined
                    }
                  />
                );
              })}
              <TouchableOpacity
                style={styles.addRow}
                onPress={() =>
                  setAddSheet({
                    planId: plan.id,
                    slot,
                    existingItemTypes: plan.plan_items.map((item) => item.item_type),
                  })
                }
                testID={`add-item-${slot}`}
                accessibilityRole="button"
              >
                <Text style={styles.addRowLabel}>+ Add item</Text>
              </TouchableOpacity>
            </View>
          );
        })}
      </ScrollView>

      <SwapSheet
        target={swapSheet}
        favoriteIds={favoriteIds}
        onToggleFavorite={toggleFavorite}
        onClose={() => setSwapSheet(null)}
        onPick={handleSwap}
      />
      <AddItemSheet
        target={addSheet}
        favoriteIds={favoriteIds}
        onToggleFavorite={toggleFavorite}
        onClose={() => setAddSheet(null)}
        onAdd={handleAdd}
      />
      <CarryOverSheet
        target={carrySheet}
        onClose={() => setCarrySheet(null)}
        onPick={handleCarryOver}
      />
    </View>
  );
}

function PlanItemRowView({
  item,
  busy,
  onSwap,
  onRemove,
  onMakeExtra,
}: {
  item: PlanItemRow;
  busy: boolean;
  onSwap: () => void;
  onRemove: () => void;
  onMakeExtra?: () => void;
}) {
  const label = item.status === 'needs_manual_pick' ? 'Needs a pick' : (item.dishes?.name ?? '—');
  return (
    <View style={styles.itemRow} testID={`plan-item-${item.id}`}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.itemType}>{item.item_type}</Text>
        <Text style={styles.itemDish}>
          {label}
          {item.make_extra ? '  ·  extra' : ''}
        </Text>
      </View>
      <View style={styles.itemActions}>
        <TouchableOpacity onPress={onSwap} disabled={busy} testID={`swap-${item.id}`}>
          <Text style={styles.actionLabel}>Swap</Text>
        </TouchableOpacity>
        {onMakeExtra && (
          <TouchableOpacity onPress={onMakeExtra} disabled={busy} testID={`extra-${item.id}`}>
            <Text style={styles.actionLabel}>Make extra</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity onPress={onRemove} disabled={busy} testID={`remove-${item.id}`}>
          <Text style={styles.actionLabelDanger}>Remove</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// MP-062: dismissible advisory only — generation-time rules are strict, edit-time rules are
// advisory (functional spec §6: "A human explicitly choosing something is the supervision").
// Neither badge below disables the row or blocks the tap (dismissing them is purely visual — see
// SwapSheet's onPick, unchanged by dismissedDishIds); they're informational text next to a choice
// the user can still make, with a way to clear the note once it's been seen.
function AdvisoryBadges({
  candidate,
  dismissed,
  onDismiss,
}: {
  candidate: SwapCandidate;
  dismissed: boolean;
  onDismiss: () => void;
}) {
  const hasAdvisory =
    candidate.used_this_week || candidate.used_recently || candidate.exceeds_nonveg_quota;
  if (!hasAdvisory || dismissed) {
    return null;
  }
  return (
    <View style={styles.badgeRow}>
      {candidate.used_this_week && <Text style={styles.badge}>Already used this week</Text>}
      {candidate.used_recently && <Text style={styles.badge}>Used in the last 10 days</Text>}
      {candidate.exceeds_nonveg_quota && (
        <Text style={styles.badge}>Over your non-veg quota this week</Text>
      )}
      <TouchableOpacity
        onPress={onDismiss}
        hitSlop={8}
        testID={`dismiss-badges-${candidate.dish_id}`}
      >
        <Text style={styles.badgeDismiss}>×</Text>
      </TouchableOpacity>
    </View>
  );
}

function FavoriteStar({
  dishId,
  isFavorite,
  onToggle,
}: {
  dishId: string;
  isFavorite: boolean;
  onToggle: (dishId: string) => void;
}) {
  return (
    <TouchableOpacity
      onPress={() => onToggle(dishId)}
      hitSlop={8}
      testID={`favorite-${dishId}`}
      accessibilityRole="button"
      accessibilityLabel={isFavorite ? 'Remove favorite' : 'Add favorite'}
    >
      <Text style={isFavorite ? styles.starFilled : styles.starEmpty}>
        {isFavorite ? '★' : '☆'}
      </Text>
    </TouchableOpacity>
  );
}

function SwapSheet({
  target,
  favoriteIds,
  onToggleFavorite,
  onClose,
  onPick,
}: {
  target: SwapSheetState;
  favoriteIds: Set<string>;
  onToggleFavorite: (dishId: string) => void;
  onClose: () => void;
  onPick: (planItemId: string, dishId: string, dishName: string) => void;
}) {
  const [candidates, setCandidates] = useState<SwapCandidate[] | null>(null);
  const [dismissedDishIds, setDismissedDishIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!target) {
      // Resets the sheet's own list to loading-state for its next open, not a value derived
      // from an external system — the same "state in effect" the rest of this codebase already
      // accepts for a close-triggered reset (see WeekPlanScreen.tsx's matching case).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCandidates(null);
      setDismissedDishIds(new Set());
      return;
    }
    let cancelled = false;
    supabase
      .rpc('list_swap_candidates', { target_plan_item_id: target.planItemId })
      .then(({ data }) => {
        if (!cancelled) {
          setCandidates((data ?? []) as SwapCandidate[]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [target]);

  return (
    <BottomSheet visible={!!target} onClose={onClose}>
      <Text style={styles.sheetTitle}>Swap {target?.itemType}</Text>
      <ScrollView style={{ maxHeight: 420 }} testID="swap-candidate-list">
        {candidates === null && <Text style={styles.infoBody}>Loading options…</Text>}
        {candidates?.length === 0 && (
          <Text style={styles.infoBody}>No other options fit your dietary restrictions.</Text>
        )}
        {candidates?.map((candidate) => (
          <View key={candidate.dish_id} style={styles.candidateRow}>
            <TouchableOpacity
              style={{ flex: 1 }}
              onPress={() => target && onPick(target.planItemId, candidate.dish_id, candidate.name)}
              testID={`candidate-${candidate.dish_id}`}
            >
              <Text style={styles.candidateName}>{candidate.name}</Text>
              <AdvisoryBadges
                candidate={candidate}
                dismissed={dismissedDishIds.has(candidate.dish_id)}
                onDismiss={() =>
                  setDismissedDishIds((current) => new Set(current).add(candidate.dish_id))
                }
              />
            </TouchableOpacity>
            <FavoriteStar
              dishId={candidate.dish_id}
              isFavorite={favoriteIds.has(candidate.dish_id)}
              onToggle={onToggleFavorite}
            />
          </View>
        ))}
      </ScrollView>
    </BottomSheet>
  );
}

function AddItemSheet({
  target,
  favoriteIds,
  onToggleFavorite,
  onClose,
  onAdd,
}: {
  target: AddSheetState;
  favoriteIds: Set<string>;
  onToggleFavorite: (dishId: string) => void;
  onClose: () => void;
  onAdd: (planId: string, itemType: ItemType, dish: DishOption) => void;
}) {
  const [itemType, setItemType] = useState<ItemType | null>(null);
  const [dishes, setDishes] = useState<DishOption[] | null>(null);

  useEffect(() => {
    // Resets the sheet's own step (item-type picker vs. dish list) for its next open.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setItemType(null);
    setDishes(null);
  }, [target]);

  useEffect(() => {
    if (!itemType || !target) {
      return;
    }
    let cancelled = false;
    (async () => {
      const [dishesResult, profileResult] = await Promise.all([
        supabase
          .from('dishes')
          .select('id, name, veg_or_nonveg, dietary_flags')
          .eq('item_type', itemType),
        supabase.auth
          .getUser()
          .then(({ data }) =>
            data.user
              ? supabase
                  .from('user_profiles')
                  .select('dietary_restrictions')
                  .eq('id', data.user.id)
                  .single()
              : null,
          ),
      ]);
      if (cancelled) {
        return;
      }
      const userRestrictions = (profileResult?.data?.dietary_restrictions ?? []) as string[];
      const safe = ((dishesResult.data ?? []) as DishOption[]).filter(
        (dish) => !dish.dietary_flags.some((flag) => userRestrictions.includes(flag)),
      );
      setDishes(safe);
    })();
    return () => {
      cancelled = true;
    };
  }, [itemType, target]);

  // PR review fix (MP-060 AC): add is for a *missing* item type only — offering a type the slot
  // already has would just be rejected by add_plan_item_to_slot's own guard, and (before that
  // guard existed) silently produced a second ordinary item of that type in the slot.
  const addableTypes = ADDABLE_ITEM_TYPES.filter(
    (option) => !target?.existingItemTypes.includes(option),
  );

  return (
    <BottomSheet visible={!!target} onClose={onClose}>
      <Text style={styles.sheetTitle}>Add to {target?.slot}</Text>
      {!itemType ? (
        <View style={styles.chipRow}>
          {addableTypes.length === 0 && (
            <Text style={styles.infoBody}>This slot already has every item type.</Text>
          )}
          {addableTypes.map((option) => (
            <TouchableOpacity
              key={option}
              style={styles.chip}
              onPress={() => setItemType(option)}
              testID={`item-type-${option}`}
            >
              <Text style={styles.chipLabel}>{option}</Text>
            </TouchableOpacity>
          ))}
        </View>
      ) : (
        <ScrollView style={{ maxHeight: 380 }} testID="add-dish-list">
          {dishes === null && <Text style={styles.infoBody}>Loading dishes…</Text>}
          {dishes?.length === 0 && (
            <Text style={styles.infoBody}>Nothing fits your dietary restrictions.</Text>
          )}
          {dishes?.map((dish) => (
            <View key={dish.id} style={styles.candidateRow}>
              <TouchableOpacity
                style={{ flex: 1 }}
                onPress={() => target && onAdd(target.planId, itemType, dish)}
                testID={`add-dish-${dish.id}`}
              >
                <Text style={styles.candidateName}>{dish.name}</Text>
              </TouchableOpacity>
              <FavoriteStar
                dishId={dish.id}
                isFavorite={favoriteIds.has(dish.id)}
                onToggle={onToggleFavorite}
              />
            </View>
          ))}
        </ScrollView>
      )}
    </BottomSheet>
  );
}

function CarryOverSheet({
  target,
  onClose,
  onPick,
}: {
  target: CarrySheetState;
  onClose: () => void;
  onPick: (sourcePlanItemId: string, targetPlanId: string) => void;
}) {
  return (
    <BottomSheet visible={!!target} onClose={onClose}>
      <Text style={styles.sheetTitle}>Carry {target?.itemType}</Text>
      <Text style={styles.infoBody}>
        Reuses the same dish on purpose — it won&apos;t count as a repeat.
      </Text>
      {target?.targetPlanId ? (
        <TouchableOpacity
          style={styles.chip}
          onPress={() => onPick(target.sourcePlanItemId, target.targetPlanId as string)}
          testID="carry-target-next-slot"
        >
          <Text style={styles.chipLabel}>Carry into {target.targetSlotLabel}</Text>
        </TouchableOpacity>
      ) : (
        <Text style={styles.infoBody}>No later slot today to carry this into.</Text>
      )}
    </BottomSheet>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.ground },
  scroll: { padding: spacing.xl, paddingBottom: 48, gap: spacing.md },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.md,
    backgroundColor: colors.ground,
  },
  slotCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  slotHeading: {
    fontFamily: fonts.bodyRegular,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
    color: colors.textMuted,
  },
  itemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  itemType: {
    fontFamily: fonts.bodyRegular,
    fontSize: 10,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    color: colors.textMuted,
  },
  itemDish: {
    fontFamily: fonts.displayLight,
    fontSize: 17,
    color: colors.textPrimary,
  },
  itemActions: { flexDirection: 'row', gap: spacing.md },
  actionLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: colors.leaf,
  },
  actionLabelDanger: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: colors.textMuted,
  },
  addRow: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  addRowLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: colors.leaf,
  },
  infoTitle: {
    fontFamily: fonts.displayRegular,
    fontSize: 20,
    color: colors.textPrimary,
  },
  infoBody: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
    paddingVertical: spacing.sm,
  },
  primaryButton: {
    minHeight: 48,
    paddingHorizontal: spacing.lg,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
  },
  sheetTitle: {
    fontFamily: fonts.displayLight,
    fontSize: 24,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  candidateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  starFilled: {
    fontSize: 18,
    color: colors.leaf,
  },
  starEmpty: {
    fontSize: 18,
    color: colors.textMuted,
  },
  candidateName: {
    fontFamily: fonts.bodyRegular,
    fontSize: 15,
    color: colors.textPrimary,
  },
  badgeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexWrap: 'wrap' },
  badge: {
    fontFamily: fonts.bodyRegular,
    fontSize: 11,
    color: colors.textMuted,
    backgroundColor: colors.accentTintHover,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radii.pill,
  },
  badgeDismiss: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textMuted,
  },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radii.pill,
  },
  chipLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: colors.textPrimary,
  },
});
