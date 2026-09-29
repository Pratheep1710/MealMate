import {
  CHRONOLOGICAL_SLOTS,
  kickerFor,
  nextRelevantSlots,
  phaseFor,
  rollingDays,
  SLOT_META,
} from '../rollingDays';

describe('rollingDays', () => {
  it('returns today plus the next five days, in order', () => {
    const today = new Date(2026, 7, 27); // Thu 27 Aug 2026
    const days = rollingDays(today);

    expect(days).toHaveLength(6);
    expect(days.map((d) => d.iso)).toEqual([
      '2026-08-27',
      '2026-08-28',
      '2026-08-29',
      '2026-08-30',
      '2026-08-31',
      '2026-09-01',
    ]);
    expect(days[0].dayName).toBe('Thu');
    expect(days[5].dayName).toBe('Tue');
  });

  it('crosses a month boundary correctly', () => {
    const days = rollingDays(new Date(2026, 7, 30));
    expect(days.map((d) => d.iso)).toContain('2026-09-01');
    expect(days.map((d) => d.iso)).toContain('2026-09-04');
  });
});

describe('kickerFor', () => {
  it('formats as "Weekday D Month"', () => {
    expect(kickerFor(new Date(2026, 7, 27))).toBe('Thu 27 August');
  });
});

describe('CHRONOLOGICAL_SLOTS', () => {
  it('orders the day spine by actual time of day, not the DB enum order', () => {
    // SLOTS (DB order) is morning, afternoon, night, snack_1, snack_2, snack_3 — that would
    // render as 6:40, 12:45, 19:45, then 10:30, 16:15, 21:30, which is out of order.
    expect(CHRONOLOGICAL_SLOTS).toEqual([
      'morning',
      'snack_1',
      'afternoon',
      'snack_2',
      'night',
      'snack_3',
    ]);
    const hours = CHRONOLOGICAL_SLOTS.map((slot) => SLOT_META[slot].hour);
    expect(hours).toEqual([...hours].sort((a, b) => a - b));
  });
});

describe('phaseFor', () => {
  it('marks earlier slots as past and the current one as now', () => {
    expect(phaseFor('morning', 13)).toBe('past');
    expect(phaseFor('afternoon', 13)).toBe('now');
    expect(phaseFor('night', 13)).toBe('upcoming');
  });

  it('treats every slot as upcoming before the first slot of the day', () => {
    expect(phaseFor('morning', 5)).toBe('upcoming');
    expect(phaseFor('night', 5)).toBe('upcoming');
  });

  it('keeps the last slot as now for the rest of the night', () => {
    expect(phaseFor('snack_3', 23)).toBe('now');
  });
});

describe('nextRelevantSlots', () => {
  it("returns the current slot plus the next one when it's mid-afternoon", () => {
    // 17:00 -> snack_2 (16:15) is 'now', night (19:45) is the next upcoming slot.
    const result = nextRelevantSlots(new Date(2026, 7, 27, 17, 0));

    expect(result.date.toDateString()).toBe(new Date(2026, 7, 27).toDateString());
    expect(result.slots).toEqual(['snack_2', 'night']);
  });

  it('returns the first two slots of the day before any slot has started', () => {
    // 3:00am -> nothing has started yet; the first two chronological slots are next.
    const result = nextRelevantSlots(new Date(2026, 7, 27, 3, 0));

    expect(result.date.toDateString()).toBe(new Date(2026, 7, 27).toDateString());
    expect(result.slots).toEqual(['morning', 'snack_1']);
  });

  it('rolls over to tomorrow morning + afternoon once the last slot of the day has started', () => {
    // Explicit late-night edge case: onboarding at/after snack_3 (21:30) has nothing "upcoming"
    // left for today, so this must not just hand back that one already-started slot.
    const result = nextRelevantSlots(new Date(2026, 7, 27, 21, 30));

    expect(result.date.toDateString()).toBe(new Date(2026, 7, 28).toDateString());
    expect(result.slots).toEqual(['morning', 'afternoon']);
  });

  it('still rolls to tomorrow well after midnight the same "night"', () => {
    const result = nextRelevantSlots(new Date(2026, 7, 27, 23, 45));

    expect(result.date.toDateString()).toBe(new Date(2026, 7, 28).toDateString());
    expect(result.slots).toEqual(['morning', 'afternoon']);
  });

  it('rolls a late-night onboarding across a month boundary correctly', () => {
    const result = nextRelevantSlots(new Date(2026, 7, 31, 22, 0));

    expect(result.date.toDateString()).toBe(new Date(2026, 8, 1).toDateString());
  });
});
