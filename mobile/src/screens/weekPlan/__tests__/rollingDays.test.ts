import { CHRONOLOGICAL_SLOTS, kickerFor, phaseFor, rollingDays, SLOT_META } from '../rollingDays';

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
