// The design pass (Claude Design project b56ee743) anchors the plan view on "today" plus the next
// five days, rather than a fixed Monday-Sunday grid — a rolling "what's coming up" window. This is
// independent of grocery_list_snapshot's Monday-anchored week_start (mobile/src/lib/week.ts), which
// stays as-is since that's a backend storage key, not a display choice.

export const SLOTS = ['morning', 'afternoon', 'night', 'snack_1', 'snack_2', 'snack_3'] as const;
export type Slot = (typeof SLOTS)[number];

export const SLOT_META: Record<Slot, { label: string; time: string; hour: number }> = {
  morning: { label: 'Morning', time: '6:40', hour: 6 + 40 / 60 },
  snack_1: { label: 'Mid-morning', time: '10:30', hour: 10.5 },
  afternoon: { label: 'Afternoon', time: '12:45', hour: 12.75 },
  snack_2: { label: 'Evening', time: '16:15', hour: 16.25 },
  night: { label: 'Night', time: '19:45', hour: 19.75 },
  snack_3: { label: 'Late', time: '21:30', hour: 21.5 },
};

// SLOTS is the DB's canonical enum order (matches meal_plans_slot_check), not chronological — it's
// fine as a lookup key order, but anything that *renders* the day spine needs this instead, or the
// spine reads 6:40, 12:45, 19:45, then 10:30, 16:15, 21:30.
export const CHRONOLOGICAL_SLOTS: readonly Slot[] = [...SLOTS].sort(
  (a, b) => SLOT_META[a].hour - SLOT_META[b].hour,
);

export function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

export type RollingDay = {
  iso: string;
  date: Date;
  dayName: string; // 'Thu'
  dayNumber: string; // '28'
};

/** Today plus the next `count - 1` days, in order. */
export function rollingDays(today: Date, count = 6): RollingDay[] {
  return Array.from({ length: count }, (_, offset) => {
    const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() + offset);
    return {
      iso: toISODate(date),
      date,
      dayName: DAY_NAMES[date.getDay()],
      dayNumber: String(date.getDate()).padStart(2, '0'),
    };
  });
}

export function kickerFor(date: Date): string {
  return `${DAY_NAMES[date.getDay()]} ${date.getDate()} ${MONTH_NAMES[date.getMonth()]}`;
}

export type SlotPhase = 'past' | 'now' | 'upcoming';

/** Which slot is "now" is a display heuristic against fixed typical meal times (the schema has no
 * per-slot time-of-day) — mirrors the design's own fixed-time slot list. Slots before the current
 * one are 'past', the closest one at-or-before now is 'now', everything after is 'upcoming'. Before
 * the first slot of the day, nothing is 'now' yet.
 */
export function phaseFor(slot: Slot, currentHour: number): SlotPhase {
  const order = CHRONOLOGICAL_SLOTS;
  const idx = order.indexOf(slot);
  let nowIndex = -1;
  for (let i = 0; i < order.length; i++) {
    if (currentHour >= SLOT_META[order[i]].hour) {
      nowIndex = i;
    }
  }
  if (nowIndex === -1) {
    return 'upcoming';
  }
  if (idx < nowIndex) {
    return 'past';
  }
  if (idx === nowIndex) {
    return 'now';
  }
  return 'upcoming';
}

export type RelevantSlots = { date: Date; slots: Slot[] };

const MAX_RELEVANT_SLOTS = 2;

/** MP-092: which slot(s) to show right after onboarding, based on the time the user signs up —
 * the one place this decision is made, reused by WeekPlanScreen's progressive-reveal state
 * rather than redefined inline. Built on SLOT_META/phaseFor's own boundaries, not new ones.
 *
 * Late-night edge case (explicit, not incidental): once `now` reaches the day's last slot
 * (snack_3, 21:30) there is nothing left "upcoming" for today by definition — phaseFor would
 * just keep returning that one slot as 'now' for the rest of the night with nothing after it, so
 * showing it as the fallback would read as "here's a snack" rather than "here's your next meal."
 * Past that boundary this rolls to tomorrow's morning + afternoon instead.
 */
export function nextRelevantSlots(now: Date): RelevantSlots {
  const currentHour = now.getHours() + now.getMinutes() / 60;
  const lastChronologicalSlot = CHRONOLOGICAL_SLOTS[CHRONOLOGICAL_SLOTS.length - 1];
  const lastSlotHour = SLOT_META[lastChronologicalSlot].hour;

  if (currentHour >= lastSlotHour) {
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    return { date: tomorrow, slots: ['morning', 'afternoon'] };
  }

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const upcoming = CHRONOLOGICAL_SLOTS.filter((slot) => phaseFor(slot, currentHour) !== 'past');
  return { date: today, slots: upcoming.slice(0, MAX_RELEVANT_SLOTS) };
}
