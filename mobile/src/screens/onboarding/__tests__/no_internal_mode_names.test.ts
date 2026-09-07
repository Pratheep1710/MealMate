import { readdirSync, readFileSync, statSync } from 'fs';
import { join } from 'path';

// MP-025 AC: internal mode names ('Suggestion'/'Reserves' — functional spec's own words for
// planning_mode's two DB values) must never be reachable anywhere in the client — not in a
// screen's copy, not in a debug string, not in an error message. Case-sensitive by design: the
// lowercase 'suggestion'/'reserves' *values* are the real, necessary DB enum literals
// (PlanningModeScreen.tsx compares against them, OnboardingContext.tsx submits them) — those are
// implementation detail, not the internal *name* being displayed to a user, and the brief's own
// wording ("Suggestion mode"/"Reserves mode") is always capitalized like this.
const BANNED_WORDS = ['Suggestion', 'Reserves'];
const SRC_ROOT = join(__dirname, '..', '..', '..');

function collectSourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      if (entry === 'node_modules' || entry === '__tests__') {
        continue;
      }
      files.push(...collectSourceFiles(fullPath));
      continue;
    }
    if (/\.(ts|tsx)$/.test(entry)) {
      files.push(fullPath);
    }
  }
  return files;
}

describe('internal mode names never reach the client', () => {
  it('does not contain the literal words "Suggestion" or "Reserves" anywhere in mobile/src', () => {
    const offenders: { file: string; word: string }[] = [];
    for (const file of collectSourceFiles(SRC_ROOT)) {
      const contents = readFileSync(file, 'utf8');
      for (const word of BANNED_WORDS) {
        if (contents.includes(word)) {
          offenders.push({ file, word });
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
