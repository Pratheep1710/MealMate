import { PGlite } from '@electric-sql/pglite';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const migrationsDir = path.resolve(__dirname, '..', 'migrations');

// Minimal stand-in for Supabase's auth schema: real Postgres roles (authenticated / anon /
// service_role) plus an auth.uid() reading a session GUC, mirroring how Supabase's own RLS
// helper works. This lets 0006_rls_policies.sql run completely unmodified against pglite.
const AUTH_STUB_SQL = `
  create role authenticated;
  create role anon;
  create role service_role bypassrls;

  create schema auth;
  create table auth.users (
    id uuid primary key default gen_random_uuid()
  );
  create or replace function auth.uid() returns uuid as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
  $$ language sql stable security definer;

  grant usage on schema auth to authenticated, anon, service_role;
  grant execute on function auth.uid() to authenticated, anon, service_role;
  grant select, insert on auth.users to authenticated, service_role;
`;

export async function createTestDb() {
  const db = new PGlite();
  await db.exec(AUTH_STUB_SQL);

  const files = readdirSync(migrationsDir)
    .filter((f) => f.endsWith('.sql'))
    .sort();
  for (const file of files) {
    const sql = readFileSync(path.join(migrationsDir, file), 'utf8');
    try {
      await db.exec(sql);
    } catch (e) {
      throw new Error(`Migration ${file} failed: ${e.message}`);
    }
  }

  return db;
}

// Creates an auth.users row and returns its id, for use as a FK target from user_profiles.
export async function createAuthUser(db, id) {
  await db.query('insert into auth.users (id) values ($1)', [id]);
  return id;
}

export async function asUser(db, userId) {
  await db.exec('set role authenticated;');
  await db.query(`set request.jwt.claim.sub = '${userId}';`);
}

export async function asAnon(db) {
  await db.exec('set role anon;');
  await db.exec(`set request.jwt.claim.sub = '';`);
}

export async function asServiceRole(db) {
  // Actually switches to the service_role Postgres role (not just resetting to the pglite
  // superuser) so tests exercise its real privileges — catching gaps like the one this comment
  // replaces: service_role had BYPASSRLS but no table grants at all (see migration 0010), which
  // a superuser stand-in could never have surfaced since a superuser bypasses grants too.
  await db.exec('set role service_role;');
}

export async function reset(db) {
  await db.exec('reset role;');
  await db.exec(`set request.jwt.claim.sub = '';`);
}

export const USER_A = '11111111-1111-1111-1111-111111111111';
export const USER_B = '22222222-2222-2222-2222-222222222222';
