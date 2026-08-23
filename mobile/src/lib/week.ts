// MP-027: shared "current week" date math — Monday-anchored, matching the ISO week convention
// most users expect for a calendar-style plan view. Kept separate from the screen component so
// it's independently unit-testable without React Native's test renderer.

export const SLOTS = ['morning', 'afternoon', 'night', 'snack_1', 'snack_2', 'snack_3'] as const;
export type Slot = (typeof SLOTS)[number];

function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// getDay(): 0 = Sunday .. 6 = Saturday. Monday-of-the-week is today minus (getDay() - 1), with
// Sunday (0) wrapping back 6 days instead of forward.
export function currentWeekStart(today: Date): Date {
  const dayOfWeek = today.getDay();
  const diffToMonday = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() + diffToMonday);
  return monday;
}

export function weekDates(weekStart: Date): string[] {
  return Array.from({ length: 7 }, (_, offset) => {
    const date = new Date(
      weekStart.getFullYear(),
      weekStart.getMonth(),
      weekStart.getDate() + offset,
    );
    return toISODate(date);
  });
}
