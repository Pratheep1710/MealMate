import { ConfigError, loadClientConfig } from './config';

const VALID_ENV = {
  EXPO_PUBLIC_SUPABASE_URL: 'https://example.supabase.co',
  EXPO_PUBLIC_SUPABASE_ANON_KEY: 'anon-key-value',
  EXPO_PUBLIC_BACKEND_URL: 'https://example-backend.onrender.com',
} as unknown as NodeJS.ProcessEnv;

test('valid config loads', () => {
  const config = loadClientConfig(VALID_ENV);
  expect(config.supabaseUrl).toBe('https://example.supabase.co');
  expect(config.supabaseAnonKey).toBe('anon-key-value');
  expect(config.backendUrl).toBe('https://example-backend.onrender.com');
});

test('missing EXPO_PUBLIC_SUPABASE_URL throws a ConfigError naming the env var', () => {
  const env = { ...VALID_ENV, EXPO_PUBLIC_SUPABASE_URL: undefined } as unknown as NodeJS.ProcessEnv;
  expect(() => loadClientConfig(env)).toThrow(ConfigError);
  expect(() => loadClientConfig(env)).toThrow('EXPO_PUBLIC_SUPABASE_URL');
});

test('missing EXPO_PUBLIC_SUPABASE_ANON_KEY throws a ConfigError naming the env var', () => {
  const env = {
    ...VALID_ENV,
    EXPO_PUBLIC_SUPABASE_ANON_KEY: undefined,
  } as unknown as NodeJS.ProcessEnv;
  expect(() => loadClientConfig(env)).toThrow(ConfigError);
  expect(() => loadClientConfig(env)).toThrow('EXPO_PUBLIC_SUPABASE_ANON_KEY');
});

test('missing EXPO_PUBLIC_BACKEND_URL throws a ConfigError naming the env var', () => {
  const env = {
    ...VALID_ENV,
    EXPO_PUBLIC_BACKEND_URL: undefined,
  } as unknown as NodeJS.ProcessEnv;
  expect(() => loadClientConfig(env)).toThrow(ConfigError);
  expect(() => loadClientConfig(env)).toThrow('EXPO_PUBLIC_BACKEND_URL');
});

test('all missing reports every problem at once', () => {
  const env = {} as NodeJS.ProcessEnv;
  try {
    loadClientConfig(env);
    throw new Error('expected loadClientConfig to throw');
  } catch (e) {
    expect(e).toBeInstanceOf(ConfigError);
    const message = (e as Error).message;
    expect(message).toContain('EXPO_PUBLIC_SUPABASE_URL');
    expect(message).toContain('EXPO_PUBLIC_SUPABASE_ANON_KEY');
    expect(message).toContain('EXPO_PUBLIC_BACKEND_URL');
  }
});

test('an invalid URL throws a ConfigError rather than shipping null config', () => {
  const env = {
    ...VALID_ENV,
    EXPO_PUBLIC_SUPABASE_URL: 'not-a-url',
  } as unknown as NodeJS.ProcessEnv;
  expect(() => loadClientConfig(env)).toThrow(ConfigError);
});

test('an invalid backend URL throws a ConfigError rather than shipping null config', () => {
  const env = {
    ...VALID_ENV,
    EXPO_PUBLIC_BACKEND_URL: 'not-a-url',
  } as unknown as NodeJS.ProcessEnv;
  expect(() => loadClientConfig(env)).toThrow(ConfigError);
});

test('never falls back to null instead of throwing', () => {
  const env = {} as NodeJS.ProcessEnv;
  expect(() => loadClientConfig(env)).toThrow();
});
