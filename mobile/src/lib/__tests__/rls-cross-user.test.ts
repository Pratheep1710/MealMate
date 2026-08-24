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
import { connect, constants as http2Constants, type IncomingHttpHeaders } from 'node:http2';
import { Headers, Response } from 'undici';

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

// CI diagnostics isolated the hang to undici's HTTP/1.1 response-body path on GitHub's runner:
// response headers arrive immediately, but a chunked body never emits even one byte. The same
// endpoint returns its body immediately over HTTP/2 (curl negotiated h2). Compression was ruled
// out by a later run: `Accept-Encoding: identity` removed Content-Encoding entirely and the
// HTTP/1.1 body still hung. This test-only adapter buffers the HTTP/2 response and wraps it in an
// undici Response, preserving the fetch contract that supabase-js uses. Production React Native
// continues to use its native fetch implementation; only this Node/Jest live-test transport is
// replaced.
async function http2Fetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url);
  if (url.protocol !== 'https:') {
    throw new TypeError(`Live Supabase test only supports HTTPS URLs, got ${url.protocol}`);
  }

  const requestHeaders = new Headers(init.headers);
  const headers: Record<string, string> = {
    ':method': init.method ?? 'GET',
    ':path': `${url.pathname}${url.search}`,
    ':scheme': 'https',
    ':authority': url.host,
  };
  for (const [name, value] of requestHeaders.entries()) {
    // HTTP/2 forbids connection-specific headers.
    if (
      !['connection', 'keep-alive', 'proxy-connection', 'transfer-encoding', 'upgrade'].includes(
        name,
      )
    ) {
      headers[name] = value;
    }
  }

  return new Promise<Response>((resolve, reject) => {
    const session = connect(url.origin);
    const chunks: Buffer[] = [];
    let responseHeaders: IncomingHttpHeaders = {};
    let settled = false;

    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      init.signal?.removeEventListener('abort', abort);
      session.close();
      if (error) reject(error);
    };
    const abort = () => {
      const error = new Error('Supabase live-test request aborted');
      error.name = 'AbortError';
      request.close(http2Constants.NGHTTP2_CANCEL);
      finish(error);
    };

    const request = session.request(headers);
    request.on('response', (receivedHeaders) => {
      responseHeaders = receivedHeaders;
    });
    request.on('data', (chunk: Buffer | Uint8Array) => {
      chunks.push(Buffer.from(chunk));
    });
    request.on('end', () => {
      const status = Number(responseHeaders[':status'] ?? 500);
      const responseHeaderBag = new Headers();
      for (const [name, value] of Object.entries(responseHeaders)) {
        if (name.startsWith(':') || value === undefined) continue;
        for (const item of Array.isArray(value) ? value : [value]) {
          responseHeaderBag.append(name, String(item));
        }
      }
      settled = true;
      init.signal?.removeEventListener('abort', abort);
      session.close();
      resolve(new Response(Buffer.concat(chunks), { status, headers: responseHeaderBag }));
    });
    request.on('error', (error) => finish(error));
    session.on('error', (error) => finish(error));

    if (init.signal?.aborted) {
      abort();
      return;
    }
    init.signal?.addEventListener('abort', abort, { once: true });

    if (init.body == null) {
      request.end();
    } else if (typeof init.body === 'string' || init.body instanceof Uint8Array) {
      request.end(init.body);
    } else if (init.body instanceof URLSearchParams) {
      request.end(init.body.toString());
    } else {
      request.destroy(new TypeError('Unsupported request body type in Supabase live-test adapter'));
    }
  });
}

function timedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const timeoutSignal = AbortSignal.timeout(15000);
  const signal = init.signal ? AbortSignal.any([init.signal, timeoutSignal]) : timeoutSignal;
  return http2Fetch(input, { ...init, signal });
}

function createLiveClient() {
  return createClient(SUPABASE_URL!, SUPABASE_ANON_KEY!, {
    global: { fetch: timedFetch as unknown as typeof fetch },
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
