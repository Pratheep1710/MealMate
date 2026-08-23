// Review fix (PR #1): app.config.ts previously read these straight into `extra` with `?? null`,
// so a missing env var silently became `null` and the app booted anyway, failing later with an
// opaque integration error the first time something touched Supabase. This is the client-side
// half of MP-014's fail-fast contract (backend/app/config.py) — same idea, same shape: validate
// once at config-evaluation time, throw an actionable message naming the env var, never the value.
//
// Plain JS, not TS: Expo's app.config.ts loader transpiles the entry file on the fly but can't
// `require()` a sibling .ts file (it fails with "Cannot find module './config'" since no .js
// exists on disk for Node to resolve). A .js file resolves normally. `allowJs` in
// expo/tsconfig.base means this still gets picked up by `tsc --noEmit` from app.config.ts's
// import, and config.test.ts type-checks its calls into this module normally.

export class ConfigError extends Error {}

/**
 * @param {NodeJS.ProcessEnv} [env]
 * @returns {{ supabaseUrl: string, supabaseAnonKey: string }}
 */
export function loadClientConfig(env = process.env) {
  const problems = [];

  const url = env.EXPO_PUBLIC_SUPABASE_URL;
  if (!url) {
    problems.push('  - EXPO_PUBLIC_SUPABASE_URL is missing');
  } else {
    try {
      new URL(url);
    } catch {
      problems.push('  - EXPO_PUBLIC_SUPABASE_URL is not a valid URL');
    }
  }

  const anonKey = env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
  if (!anonKey) {
    problems.push('  - EXPO_PUBLIC_SUPABASE_ANON_KEY is missing');
  }

  if (problems.length > 0) {
    throw new ConfigError(
      'Mobile config is invalid — fix the following environment variables:\n' + problems.join('\n'),
    );
  }

  return { supabaseUrl: url, supabaseAnonKey: anonKey };
}
