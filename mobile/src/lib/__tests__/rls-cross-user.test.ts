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
import dns from 'node:dns';
import { Headers, fetch as undiciFetch } from 'undici';

// GitHub Actions runners sometimes have broken or very slow IPv6 egress — a request to a
// dual-stack host then hangs waiting on an IPv6 connection attempt instead of falling back to
// IPv4 quickly, which looks identical to a dead network from the test's side (this project has
// hit the same class of IPv6-only-host issue before — see supabase/apply_migrations.py's
// docstring). Preferring IPv4 resolution avoids the hang outright.
dns.setDefaultResultOrder('ipv4first');

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

// Diagnostic instrumentation (see the commit that added it) proved the hang isn't network/DNS at
// all: the connection, TLS handshake, and response headers all come back in ~500ms every time —
// the hang is specifically in consuming the response *body* (res.text()/res.json() never
// resolves). @supabase/auth-js builds its request `headers` via `new Headers(...)` against
// whatever the *global* Headers constructor is — which, under jest-expo, is the RN/web polyfill
// merged in by @react-native/jest-preset's setupFiles, not undici's own. Normalizing every header
// through undici's own Headers class avoids passing it a foreign-constructor instance, but wasn't
// the actual fix (kept anyway as harmless defense in depth).
//
// The actual root cause, found by comparing this fetch's response headers against a curl request
// to the identical endpoint (added as a CI diagnostic step): curl's plain request got back a
// response with NO Content-Encoding header — Cloudflare/Supabase served it uncompressed. fetch()
// automatically sends `Accept-Encoding: gzip, deflate, br`, so the same endpoint served *this*
// request `content-encoding: gzip` instead — and undici's automatic gzip decompression is what
// hangs (confirmed: headers arrive in ~500ms either way, but only the compressed response's body
// never resolves). Forcing `Accept-Encoding: identity` here matches curl's successful uncompressed
// path exactly, sidestepping undici's decompression path entirely.
function timedFetch(
  input: Parameters<typeof undiciFetch>[0],
  init: Parameters<typeof undiciFetch>[1] = {},
) {
  const timeoutSignal = AbortSignal.timeout(15000);
  const signal = init.signal
    ? AbortSignal.any([init.signal as AbortSignal, timeoutSignal])
    : timeoutSignal;
  const headers = new Headers(init.headers as HeadersInit | undefined);
  headers.set('accept-encoding', 'identity');
  return undiciFetch(input, { ...init, headers, signal });
}

function createLiveClient() {
  return createClient(SUPABASE_URL!, SUPABASE_ANON_KEY!, {
    global: { fetch: timedFetch as unknown as typeof fetch },
  });
}

// DIAGNOSTIC (temporary): the three tests below have hung for their full timeout budget across
// several fix attempts (undici fetch, IPv4 DNS preference, a fast per-request abort) with zero
// change in behavior or timing — meaning whatever's hanging isn't in the network/fetch layer at
// all (ruled out by reading @supabase/auth-js's source directly: isBrowser() is false here, so
// storage already falls back to an in-memory adapter, and the legacy lock path never engages
// since no `lock` option is passed). console.log calls are captured by Jest per-test and printed
// even when a test times out, so a raw timedFetch call plus explicit timing checkpoints around
// each operation should show exactly where execution actually stops.
let diagStart = 0;
function logStep(label: string) {
  const now = Date.now();
  console.log(`[diag] ${label} at +${diagStart ? now - diagStart : 0}ms`);
  if (!diagStart) diagStart = now;
}

describeLive('cross-user RLS denial (live Supabase project, mobile client path)', () => {
  it('DIAGNOSTIC: raw timedFetch to the auth token endpoint', async () => {
    diagStart = Date.now();
    logStep('starting raw fetch');
    const res = await timedFetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: { apikey: SUPABASE_ANON_KEY!, 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: USER_A_EMAIL, password: USER_A_PASSWORD }),
    });
    logStep(`got response, status ${res.status}`);
    logStep(`headers: ${JSON.stringify([...res.headers.entries()])}`);

    // Manually pump the stream instead of res.text() — this shows whether ANY bytes ever arrive
    // (a slow trickle vs. a complete dead stop from byte zero) and, via the progress timer, how
    // long the process is actually stuck for before Jest's timeout cuts it off.
    const reader = res.body!.getReader();
    const chunks: Uint8Array[] = [];
    const progressTimer = setInterval(() => {
      logStep(`still reading body stream, ${chunks.length} chunk(s) so far`);
    }, 3000);
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        logStep(`got chunk of ${value.length} bytes`);
      }
    } finally {
      clearInterval(progressTimer);
    }
    const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
    logStep(`stream done, total ${totalLength} bytes`);
    expect(res.status).toBe(200);
  }, 20000);

  it("user B cannot read user A's profile row", async () => {
    diagStart = Date.now();
    logStep('creating clientA');
    const clientA = createLiveClient();
    logStep('calling signInWithPassword for A');
    const { data: signInA, error: signInAError } = await clientA.auth.signInWithPassword({
      email: USER_A_EMAIL!,
      password: USER_A_PASSWORD!,
    });
    logStep('signInWithPassword for A returned');
    expect(signInAError).toBeNull();
    const userAId = signInA.user!.id;

    logStep('creating clientB');
    const clientB = createLiveClient();
    logStep('calling signInWithPassword for B');
    const { error: signInBError } = await clientB.auth.signInWithPassword({
      email: USER_B_EMAIL!,
      password: USER_B_PASSWORD!,
    });
    logStep('signInWithPassword for B returned');
    expect(signInBError).toBeNull();

    // User B queries user A's row by id directly (not `.eq('id', own id)`) — if RLS were
    // misconfigured this would leak cross-user data instead of coming back empty.
    logStep('querying user_profiles as B');
    const { data, error } = await clientB.from('user_profiles').select('id').eq('id', userAId);
    logStep('query returned');

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
