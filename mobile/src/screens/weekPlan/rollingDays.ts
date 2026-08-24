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

function toISODate(date: Date): string {
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
  // SLOTS is the DB's canonical (non-chronological) order — sort by actual time-of-day here so
  // "the last slot at-or-before now" is found correctly regardless of enum declaration order.
  const order = [...SLOTS].sort((a, b) => SLOT_META[a].hour - SLOT_META[b].hour);
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
