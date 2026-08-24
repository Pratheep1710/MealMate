import { useEffect, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { BottomSheet } from '../components/BottomSheet';
import { RefreshIcon } from '../components/icons';
import { PulseRing } from '../components/PulseRing';
import { Shimmer } from '../components/Shimmer';
import { supabase } from '../lib/supabase';
import { type CachedPayload, loadCache, saveCache } from '../lib/weekCache';
import { colors, fonts, radii, spacing } from '../theme/tokens';
import {
  kickerFor,
  phaseFor,
  type RollingDay,
  rollingDays,
  SLOT_META,
  SLOTS,
  type Slot,
} from './weekPlan/rollingDays';

// MP-027, redesigned per the Claude Design pass (project b56ee743, "Meal Planner.dc.html"): the
// "day spine" for today, a rolling six-day window, real RLS-scoped Supabase reads
// (0006_rls_policies.sql) — no mocked/local data — plus the pending ("still cooking") and offline
// (cached-copy) states the design calls out as real product states, not just the happy path.
//
// Swap/skip/regenerate are visually present (tapping a slot or "New ideas" opens the right sheet)
// but inert this round: there's no dish catalog yet (MP-015-020 blocked) and no generation engine
// (MP-034/038-044 blocked), so there is nothing real to offer. Each sheet says so plainly instead
// of pretending to work.
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

type ViewState =
  | { kind: 'loading' }
  | { kind: 'ready'; plans: MealPlanRow[] }
  | { kind: 'offline'; cached: CachedPayload<MealPlanRow[]> | null };

const CACHE_KEY = 'week-plan';
const MAIN_ITEM_TYPES = new Set(['rice', 'tiffin']);
const MIN_TAP_TARGET = 48;

function slotKey(planDate: string, slot: string): string {
  return `${planDate}|${slot}`;
}

function byPlansMap(plans: MealPlanRow[]): Map<string, MealPlanRow> {
  const map = new Map<string, MealPlanRow>();
  for (const row of plans) {
    map.set(slotKey(row.plan_date, row.slot), row);
  }
  return map;
}

function orderedItems(items: PlanItemRow[]): PlanItemRow[] {
  return [...items].sort((a, b) => {
    const aMain = MAIN_ITEM_TYPES.has(a.item_type) ? 0 : 1;
    const bMain = MAIN_ITEM_TYPES.has(b.item_type) ? 0 : 1;
    return aMain - bMain;
  });
}

function composeLine(items: PlanItemRow[]): string | null {
  if (items.length === 0) {
    return null;
  }
  return orderedItems(items)
    .map((item) =>
      item.status === 'needs_manual_pick' ? 'Needs a pick' : (item.dishes?.name ?? 'Unknown dish'),
    )
    .join(', ');
}

async function fetchRollingWindow(days: RollingDay[]): Promise<MealPlanRow[]> {
  const { data, error } = await supabase
    .from('meal_plans')
    .select(
      'id, plan_date, slot, is_skipped, plan_items(id, item_type, status, make_extra, dishes(name))',
    )
    .gte('plan_date', days[0].iso)
    .lte('plan_date', days[days.length - 1].iso);

  if (error) {
    throw error;
  }
  return (data ?? []) as unknown as MealPlanRow[];
}

export function WeekPlanScreen() {
  const days = useMemo(() => rollingDays(new Date()), []);
  const [view, setView] = useState<ViewState>({ kind: 'loading' });
  const [slotSheet, setSlotSheet] = useState<{ day: RollingDay; slot: Slot } | null>(null);
  const [infoSheetOpen, setInfoSheetOpen] = useState(false);

  const load = async () => {
    setView({ kind: 'loading' });
    try {
      const plans = await fetchRollingWindow(days);
      setView({ kind: 'ready', plans });
      await saveCache(CACHE_KEY, plans);
    } catch {
      const cached = await loadCache<MealPlanRow[]>(CACHE_KEY);
      setView({ kind: 'offline', cached });
    }
  };

  useEffect(() => {
    // `load` is deliberately shared between the initial mount fetch and the offline view's "Try
    // again" button — same request, two triggers — which is what react-hooks/set-state-in-effect
    // flags here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    // `load` is intentionally omitted: it's stable in practice (only closes over `days`, itself
    // derived from `new Date()` once at mount) and including it would refetch on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (view.kind === 'loading') {
    return (
      <ScrollView contentContainerStyle={styles.scroll} testID="week-plan-loading">
        <Header today={days[0]} onOpenInfo={() => setInfoSheetOpen(true)} busy />
        <TodaySkeleton />
      </ScrollView>
    );
  }

  if (view.kind === 'offline') {
    return (
      <OfflineView
        cached={view.cached}
        today={days[0]}
        onRetry={load}
        onUseCache={(plans) => setView({ kind: 'ready', plans })}
      />
    );
  }

  const plansByKey = byPlansMap(view.plans);
  const todayRows = SLOTS.map((slot) => plansByKey.get(slotKey(days[0].iso, slot)) ?? null);
  const todayHasAnyPlan = todayRows.some((row) => row !== null);

  return (
    <View style={styles.container} testID="week-plan-ready">
      <ScrollView contentContainerStyle={styles.scroll}>
        <Header today={days[0]} onOpenInfo={() => setInfoSheetOpen(true)} busy={false} />

        {todayHasAnyPlan ? (
          <View style={styles.card}>
            {SLOTS.map((slot, index) => {
              const row = plansByKey.get(slotKey(days[0].iso, slot)) ?? null;
              return (
                <SlotRow
                  key={slot}
                  slot={slot}
                  row={row}
                  isLast={index === SLOTS.length - 1}
                  onPress={row ? () => setSlotSheet({ day: days[0], slot }) : undefined}
                />
              );
            })}
          </View>
        ) : (
          <>
            <StillCookingCard />
            <Text style={styles.sectionLabel}>Shape of a day</Text>
            <TodaySkeleton />
          </>
        )}

        <View style={styles.sectionDividerRow}>
          <Text style={styles.sectionLabel}>Rest of the week</Text>
          <View style={styles.sectionDividerLine} />
        </View>

        {days.slice(1).map((day) => (
          <RestOfWeekRow key={day.iso} day={day} plansByKey={plansByKey} />
        ))}

        <Text style={styles.footerNote}>A shape for the day — not a checklist.</Text>
      </ScrollView>

      <SlotDetailSheet
        target={slotSheet}
        row={
          slotSheet ? (plansByKey.get(slotKey(slotSheet.day.iso, slotSheet.slot)) ?? null) : null
        }
        onClose={() => setSlotSheet(null)}
      />
      <InfoSheet visible={infoSheetOpen} onClose={() => setInfoSheetOpen(false)} />
    </View>
  );
}

function Header({
  today,
  onOpenInfo,
  busy,
}: {
  today: RollingDay;
  onOpenInfo: () => void;
  busy: boolean;
}) {
  return (
    <View style={styles.headerRow}>
      <View style={{ gap: 3 }}>
        <Text style={styles.kicker}>{kickerFor(today.date)}</Text>
        <Text style={styles.title}>Today</Text>
      </View>
      <TouchableOpacity
        style={styles.newIdeasPill}
        onPress={onOpenInfo}
        testID="new-ideas-pill"
        accessibilityRole="button"
      >
        <RefreshIcon size={15} color={colors.leaf} />
        <Text style={styles.newIdeasLabel}>{busy ? 'Loading…' : 'New ideas'}</Text>
      </TouchableOpacity>
    </View>
  );
}

function nodeStyleFor(phase: 'past' | 'now' | 'upcoming', skipped: boolean) {
  if (skipped) {
    return styles.nodeSkipped;
  }
  if (phase === 'past') {
    return styles.nodePast;
  }
  if (phase === 'upcoming') {
    return styles.nodeUpcoming;
  }
  return null; // 'now' renders PulseRing instead of a plain node
}

function SlotRow({
  slot,
  row,
  isLast,
  onPress,
}: {
  slot: Slot;
  row: MealPlanRow | null;
  isLast: boolean;
  onPress?: () => void;
}) {
  const meta = SLOT_META[slot];
  const currentHour = new Date().getHours() + new Date().getMinutes() / 60;
  const phase = phaseFor(slot, currentHour);
  const skipped = row?.is_skipped ?? false;
  const line = row ? composeLine(row.plan_items) : null;

  const label = skipped ? `${meta.label} · your call` : meta.label;
  const dishText = skipped ? 'Cooking something of your own' : (line ?? '—');

  const content = (
    <View style={styles.slotRow}>
      <Text style={styles.slotTime}>{meta.time}</Text>
      <View style={styles.slotRailColumn}>
        {!isLast && <View style={styles.rail} />}
        {phase === 'now' && !skipped ? (
          <PulseRing size={13} />
        ) : (
          <View style={[styles.nodeBase, nodeStyleFor(phase, skipped)]} />
        )}
      </View>
      <View style={styles.slotBody}>
        <Text style={styles.slotLabel}>{label}</Text>
        <Text
          style={[
            styles.slotDish,
            phase === 'now' && styles.slotDishNow,
            phase === 'past' && !skipped && styles.slotDishPast,
            skipped && styles.slotDishSkipped,
          ]}
        >
          {dishText}
        </Text>
      </View>
    </View>
  );

  if (!onPress) {
    return content;
  }
  return (
    <TouchableOpacity onPress={onPress} testID={`slot-row-${slot}`} activeOpacity={0.7}>
      {content}
    </TouchableOpacity>
  );
}

function TodaySkeleton() {
  return (
    <View style={styles.card} testID="today-skeleton">
      {SLOTS.map((slot, index) => (
        <View key={slot} style={styles.slotRow}>
          <Text style={styles.slotTime}>{SLOT_META[slot].time}</Text>
          <View style={styles.slotRailColumn}>
            {index !== SLOTS.length - 1 && <View style={styles.rail} />}
            <View style={styles.nodeSkeleton} />
          </View>
          <View style={{ flex: 1, gap: 7, paddingTop: 2 }}>
            <Shimmer width="70%" height={14} delay={index * 120} />
          </View>
        </View>
      ))}
    </View>
  );
}

function StillCookingCard() {
  return (
    <View style={styles.infoCard} testID="still-cooking-card">
      <View style={styles.steamIcon}>
        <PulseRing size={22} />
      </View>
      <View style={{ flex: 1, gap: 5 }}>
        <Text style={styles.infoCardTitle}>Putting today together</Text>
        <Text style={styles.infoCardBody}>
          Usually done by 8 PM the evening before. Nothing to do until then.
        </Text>
      </View>
    </View>
  );
}

function RestOfWeekRow({
  day,
  plansByKey,
}: {
  day: RollingDay;
  plansByKey: Map<string, MealPlanRow>;
}) {
  const mainSlots: Slot[] = ['morning', 'afternoon', 'night'];
  const snackSlots: Slot[] = ['snack_1', 'snack_2', 'snack_3'];

  const mains = mainSlots
    .map((slot) => plansByKey.get(slotKey(day.iso, slot)))
    .filter((row): row is MealPlanRow => !!row)
    .map((row) => composeLine(row.plan_items))
    .filter((line): line is string => !!line)
    .join(' · ');

  const snacks = snackSlots
    .map((slot) => plansByKey.get(slotKey(day.iso, slot)))
    .filter((row): row is MealPlanRow => !!row)
    .map((row) => composeLine(row.plan_items))
    .filter((line): line is string => !!line)
    .join(', ');

  return (
    <View style={styles.restRow} testID={`rest-of-week-${day.iso}`}>
      <View style={{ width: 52 }}>
        <Text style={styles.restDayName}>{day.dayName}</Text>
        <Text style={styles.restDayNumber}>{day.dayNumber}</Text>
      </View>
      <View style={{ flex: 1, gap: 2, minWidth: 0 }}>
        <Text style={styles.restMains} numberOfLines={1}>
          {mains || '—'}
        </Text>
        {snacks ? <Text style={styles.restSnacks}>{snacks}</Text> : null}
      </View>
    </View>
  );
}

function SlotDetailSheet({
  target,
  row,
  onClose,
}: {
  target: { day: RollingDay; slot: Slot } | null;
  row: MealPlanRow | null;
  onClose: () => void;
}) {
  const visible = !!target;
  const meta = target ? SLOT_META[target.slot] : null;
  const line = row ? composeLine(row.plan_items) : null;
  const skipped = row?.is_skipped ?? false;

  return (
    <BottomSheet visible={visible} onClose={onClose}>
      {meta && (
        <>
          <Text style={styles.sheetKicker}>
            {meta.label} · {meta.time}
          </Text>
          <Text style={styles.sheetTitle}>
            {skipped ? 'Cooking something of your own' : (line ?? 'Nothing planned yet')}
          </Text>
          <Text style={styles.sheetNote}>Swapping opens up once the dish list is ready.</Text>
          <TouchableOpacity style={styles.sheetPrimaryButton} onPress={onClose}>
            <Text style={styles.sheetPrimaryButtonLabel}>Close</Text>
          </TouchableOpacity>
        </>
      )}
    </BottomSheet>
  );
}

function InfoSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  return (
    <BottomSheet visible={visible} onClose={onClose}>
      <Text style={styles.sheetKicker}>Fresh ideas</Text>
      <Text style={styles.sheetTitle}>Not quite ready</Text>
      <Text style={styles.sheetNote}>
        Once the dish list is ready, this will find something new for you.
      </Text>
      <TouchableOpacity style={styles.sheetPrimaryButton} onPress={onClose}>
        <Text style={styles.sheetPrimaryButtonLabel}>Got it</Text>
      </TouchableOpacity>
    </BottomSheet>
  );
}

function OfflineView({
  cached,
  today,
  onRetry,
  onUseCache,
}: {
  cached: CachedPayload<MealPlanRow[]> | null;
  today: RollingDay;
  onRetry: () => void;
  onUseCache: (plans: MealPlanRow[]) => void;
}) {
  if (!cached) {
    return (
      <View style={styles.centered} testID="week-plan-error">
        <Text style={styles.infoCardTitle}>Couldn&apos;t load your plan</Text>
        <Text style={styles.infoCardBody}>Check your connection and try again.</Text>
        <TouchableOpacity style={styles.sheetPrimaryButton} onPress={onRetry}>
          <Text style={styles.sheetPrimaryButtonLabel}>Try again</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const savedLabel = new Date(cached.savedAt).toLocaleString(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });
  const plansByKey = byPlansMap(cached.data);

  return (
    <ScrollView contentContainerStyle={styles.scroll} testID="week-plan-offline">
      <Header today={today} onOpenInfo={() => {}} busy={false} />
      <View style={styles.infoCard}>
        <View style={{ flex: 1, gap: 10 }}>
          <Text style={styles.infoCardTitle}>Working from the saved copy</Text>
          <Text style={styles.infoCardBody}>
            The connection dropped, so this is from {savedLabel}. Nothing below is lost.
          </Text>
          <View style={styles.offlineActionsRow}>
            <TouchableOpacity style={styles.sheetSecondaryButton} onPress={onRetry}>
              <RefreshIcon size={15} color={colors.leaf} />
              <Text style={styles.sheetSecondaryButtonLabel}>Try again</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.sheetOutlineButton}
              onPress={() => onUseCache(cached.data)}
            >
              <Text style={styles.sheetOutlineButtonLabel}>Use the copy</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>

      <Text style={styles.sectionLabel}>Saved {savedLabel}</Text>
      <View style={[styles.card, { opacity: 0.72 }]}>
        {SLOTS.map((slot, index) => (
          <SlotRow
            key={slot}
            slot={slot}
            row={plansByKey.get(slotKey(today.iso, slot)) ?? null}
            isLast={index === SLOTS.length - 1}
          />
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.ground,
  },
  scroll: {
    padding: spacing.xl,
    paddingBottom: 48,
    backgroundColor: colors.ground,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.md,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    marginBottom: spacing.lg,
  },
  kicker: {
    fontFamily: fonts.bodyRegular,
    fontSize: 11,
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    color: colors.textMuted,
  },
  title: {
    fontFamily: fonts.displayLight,
    fontSize: 34,
    lineHeight: 36,
    color: colors.textPrimary,
  },
  newIdeasPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    height: 44,
    paddingHorizontal: 15,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radii.pill,
  },
  newIdeasLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.leaf,
  },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    paddingVertical: 6,
    marginBottom: spacing.sm,
  },
  slotRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    paddingVertical: 14,
    paddingHorizontal: spacing.lg,
    minHeight: MIN_TAP_TARGET,
  },
  slotTime: {
    width: 46,
    fontFamily: fonts.bodyRegular,
    fontSize: 12,
    color: colors.textMuted,
    textAlign: 'right',
    paddingTop: 3,
  },
  slotRailColumn: {
    width: 13,
    alignItems: 'center',
    alignSelf: 'stretch',
  },
  rail: {
    position: 'absolute',
    top: 10,
    bottom: -16,
    width: 1,
    backgroundColor: colors.hairline,
  },
  nodeBase: {
    marginTop: 6,
    borderRadius: 6,
  },
  nodePast: {
    width: 9,
    height: 9,
    backgroundColor: colors.steel,
  },
  nodeUpcoming: {
    width: 10,
    height: 10,
    borderWidth: 1.5,
    borderColor: colors.leaf,
    backgroundColor: colors.surface,
  },
  nodeSkipped: {
    width: 11,
    height: 11,
    borderWidth: 1.5,
    borderColor: colors.steel,
    borderStyle: 'dashed',
    backgroundColor: colors.surface,
  },
  nodeSkeleton: {
    marginTop: 6,
    width: 9,
    height: 9,
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: colors.dotOutline,
    backgroundColor: colors.ground,
  },
  slotBody: {
    flex: 1,
    gap: 3,
    paddingTop: 1,
  },
  slotLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 10,
    letterSpacing: 1,
    textTransform: 'uppercase',
    color: colors.textMuted,
  },
  slotDish: {
    fontFamily: fonts.displayLight,
    fontSize: 21,
    lineHeight: 25,
    color: colors.textPrimary,
  },
  slotDishNow: {
    fontFamily: fonts.displayRegular,
    fontSize: 23,
    lineHeight: 27,
  },
  slotDishPast: {
    color: colors.textSecondary,
  },
  slotDishSkipped: {
    color: colors.textMuted,
    fontStyle: 'italic',
  },
  sectionDividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
  },
  sectionLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 11,
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    color: colors.textMuted,
  },
  sectionDividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: colors.divider,
  },
  restRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: 56,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  restDayName: {
    fontFamily: fonts.bodySemiBold,
    fontSize: 13,
    letterSpacing: 0.5,
    color: colors.textPrimary,
  },
  restDayNumber: {
    fontFamily: fonts.bodyRegular,
    fontSize: 11,
    color: colors.textMuted,
  },
  restMains: {
    fontFamily: fonts.displayLight,
    fontSize: 17,
    lineHeight: 21,
    color: colors.textPrimary,
  },
  restSnacks: {
    fontFamily: fonts.bodyRegular,
    fontSize: 12,
    color: colors.textMuted,
  },
  footerNote: {
    fontFamily: fonts.bodyRegular,
    fontSize: 12,
    lineHeight: 18,
    color: colors.textMuted,
    marginTop: spacing.xl,
  },
  infoCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    padding: spacing.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    marginBottom: spacing.sm,
  },
  steamIcon: {
    marginTop: 2,
  },
  infoCardTitle: {
    fontFamily: fonts.displayRegular,
    fontSize: 20,
    lineHeight: 24,
    color: colors.textPrimary,
  },
  infoCardBody: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    lineHeight: 20,
    color: colors.textSecondary,
  },
  offlineActionsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  sheetKicker: {
    fontFamily: fonts.bodyRegular,
    fontSize: 10,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    color: colors.textMuted,
    marginBottom: 2,
  },
  sheetTitle: {
    fontFamily: fonts.displayLight,
    fontSize: 26,
    lineHeight: 31,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  sheetNote: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    lineHeight: 19,
    color: colors.textMuted,
    marginBottom: spacing.lg,
  },
  sheetPrimaryButton: {
    minHeight: MIN_TAP_TARGET,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sheetPrimaryButtonLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
  },
  sheetSecondaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    flex: 1,
    minHeight: MIN_TAP_TARGET,
    borderRadius: radii.md,
    backgroundColor: colors.accentTintHover,
  },
  sheetSecondaryButtonLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.leaf,
  },
  sheetOutlineButton: {
    flex: 1,
    minHeight: MIN_TAP_TARGET,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sheetOutlineButtonLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
  },
});
