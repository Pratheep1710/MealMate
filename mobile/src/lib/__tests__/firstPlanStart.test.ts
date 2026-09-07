import { computeFirstPlanStart, formatFirstPlanStart } from '../firstPlanStart';

// Mirrors backend/tests/test_planning_trigger.py's compute_first_plan_start cases exactly, same
// anchor week (2026-08-24 is a Monday), so the two implementations can be checked against the
// same expected outputs by inspection.
const MONDAY = new Date(2026, 7, 24);
const TUESDAY = new Date(2026, 7, 25);
const FRIDAY = new Date(2026, 7, 28);
const SUNDAY_NEXT_WEEK = new Date(2026, 7, 30);

describe('computeFirstPlanStart', () => {
  it('returns today when signup lands exactly on the trigger day (Suggestion)', () => {
    const result = computeFirstPlanStart(FRIDAY, 'saturday', 'suggestion');
    expect(result.toDateString()).toBe(FRIDAY.toDateString());
  });

  it('returns the upcoming trigger day for a mid-week Suggestion signup, not today', () => {
    const result = computeFirstPlanStart(TUESDAY, 'saturday', 'suggestion');
    expect(result.toDateString()).toBe(FRIDAY.toDateString());
  });

  it('returns the upcoming trigger day for a mid-week Reserves signup, not today', () => {
    const result = computeFirstPlanStart(TUESDAY, 'saturday', 'reserves');
    expect(result.toDateString()).toBe(SUNDAY_NEXT_WEEK.toDateString());
  });

  it('wraps correctly across a week boundary', () => {
    // grocery_day=Monday, Suggestion triggers the day before (Sunday). Starting from a Monday
    // itself must roll all the way to the *next* Sunday (2026-08-30), not "yesterday".
    const result = computeFirstPlanStart(MONDAY, 'monday', 'suggestion');
    const expected = new Date(2026, 7, 30);
    expect(result.toDateString()).toBe(expected.toDateString());
  });

  it('never looks more than six days out', () => {
    const days = [
      'monday',
      'tuesday',
      'wednesday',
      'thursday',
      'friday',
      'saturday',
      'sunday',
    ] as const;
    for (const mode of ['suggestion', 'reserves'] as const) {
      for (const day of days) {
        const result = computeFirstPlanStart(new Date(2026, 7, 26), day, mode);
        const diffDays = (result.getTime() - new Date(2026, 7, 26).getTime()) / 86_400_000;
        expect(diffDays).toBeGreaterThanOrEqual(0);
        expect(diffDays).toBeLessThanOrEqual(6);
      }
    }
  });
});

describe('formatFirstPlanStart', () => {
  it('labels the same calendar day as "Today"', () => {
    expect(formatFirstPlanStart(MONDAY, MONDAY)).toBe('Today');
  });

  it('formats a different day as a concrete weekday/month/day string', () => {
    const label = formatFirstPlanStart(FRIDAY, TUESDAY);
    expect(label).not.toBe('Today');
    expect(label).toContain('Friday');
  });
});
