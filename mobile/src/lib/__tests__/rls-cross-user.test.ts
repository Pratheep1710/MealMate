/**
 * MP-023 AC: "authenticated queries respect RLS" — a real cross-user denial test from the mobile
 * client, not just the backend's unit/integration coverage (backend/tests/test_config.py,
 * supabase/tests/rls.test.mjs). This is the first place RLS gets exercised through the exact path
 * a phone actually uses: supabase-js + a real signed-in JWT, not a service-role/bypass connection.
 *
 * Requires a live Supabase project (MP-006) with TWO confirmed test users (MP-012's setup only
 * provisions one) plus a user_profiles row for each — see docs/MP-023-cross-user-rls-test.md for
 * setup. Skips (not fails) without those env vars, mirroring
 * backend/tests/test_supabase_auth.py's pattern.
 *
 * Passes an explicit `fetch` (from `undici`, a devDependency) into every client instead of
 * relying on the global one: jest-expo's preset merges in @react-native/jest-preset's own
 * setupFiles, which replace global.fetch with an RN networking shim that has no real bridge to
 * talk to in a Jest/Node process — it "succeeds" with an empty/undefined response instead of
 * doing a real HTTP request, which supabase-js then fails to parse as JSON. Confirmed directly:
 * `await fetch('https://example.com')` under this test environment resolves with
 * `res.status === undefined`. No per-file Jest config escapes this, since setupFiles from a
 * preset and from the project's own config both always run.
 */
import { createClient } from '@supabase/supabase-js';
import { fetch as undiciFetch } from 'undici';

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.SUPABASE_ANON_KEY;
const USER_A_EMAIL = process.env.SUPABASE_TEST_USER_EMAIL;
const USER_A_PASSWORD = process.env.SUPABASE_TEST_USER_PASSWORD;
const USER_B_EMAIL = process.env.SUPABASE_TEST_USER_B_EMAIL;
const USER_B_PASSWORD = process.env.SUPABASE_TEST_USER_B_PASSWORD;

const hasLiveCreds = Boolean(
  SUPABASE_URL &&
  SUPABASE_ANON_KEY &&
  USER_A_EMAIL &&
  USER_A_PASSWORD &&
  USER_B_EMAIL &&
  USER_B_PASSWORD,
);

const describeLive = hasLiveCreds ? describe : describe.skip;

// Jest's default 5s per-test timeout is tuned for mocked/local work — these tests make 2-3 real
// network round-trips each (sign in as A, sign in as B, then a query) against a live Supabase
// project, which routinely exceeds that from a GitHub Actions runner.
jest.setTimeout(30000);

function createLiveClient() {
  return createClient(SUPABASE_URL!, SUPABASE_ANON_KEY!, {
    global: { fetch: undiciFetch as unknown as typeof fetch },
  });
}

describeLive('cross-user RLS denial (live Supabase project, mobile client path)', () => {
  it("user B cannot read user A's profile row", async () => {
    const clientA = createLiveClient();
    const { data: signInA, error: signInAError } = await clientA.auth.signInWithPassword({
      email: USER_A_EMAIL!,
      password: USER_A_PASSWORD!,
    });
    expect(signInAError).toBeNull();
    const userAId = signInA.user!.id;

    const clientB = createLiveClient();
    const { error: signInBError } = await clientB.auth.signInWithPassword({
      email: USER_B_EMAIL!,
      password: USER_B_PASSWORD!,
    });
    expect(signInBError).toBeNull();

    // User B queries user A's row by id directly (not `.eq('id', own id)`) — if RLS were
    // misconfigured this would leak cross-user data instead of coming back empty.
    const { data, error } = await clientB.from('user_profiles').select('id').eq('id', userAId);

    expect(error).toBeNull();
    expect(data).toEqual([]);
  });

  it("user B cannot read user A's meal_plans rows", async () => {
    const clientA = createLiveClient();
    const { data: signInA } = await clientA.auth.signInWithPassword({
      email: USER_A_EMAIL!,
      password: USER_A_PASSWORD!,
    });
    const userAId = signInA.user!.id;

    const clientB = createLiveClient();
    await clientB.auth.signInWithPassword({ email: USER_B_EMAIL!, password: USER_B_PASSWORD! });

    const { data, error } = await clientB.from('meal_plans').select('id').eq('user_id', userAId);

    expect(error).toBeNull();
    expect(data).toEqual([]);
  });

  it('user A can read their own profile row (own-data access still succeeds)', async () => {
    const clientA = createLiveClient();
    const { data: signInA } = await clientA.auth.signInWithPassword({
      email: USER_A_EMAIL!,
      password: USER_A_PASSWORD!,
    });
    const userAId = signInA.user!.id;

    const { data, error } = await clientA.from('user_profiles').select('id').eq('id', userAId);

    expect(error).toBeNull();
    expect(data).toEqual([{ id: userAId }]);
  });
});
