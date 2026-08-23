import { describe, it, expect, beforeEach } from 'vitest';
import { createTestDb, createAuthUser, USER_A } from './helpers.mjs';

// MP-007, MP-008, MP-009, MP-010, MP-011: schema migration + FK/uniqueness constraint tests.
// Runs as the pglite superuser (bypasses RLS, same as Supabase's service_role for this purpose) so
// these tests isolate structural correctness from access control — RLS itself is covered in
// rls.test.mjs.

let db;

beforeEach(async () => {
  db = await createTestDb();
  await createAuthUser(db, USER_A);
});

describe('MP-007 — dish and ingredient schema', () => {
  it('applies cleanly with PK/FK/unique constraints and track_variety/is_staple fields', async () => {
    const dish = await db.query(
      `insert into dishes (name, item_type, veg_or_nonveg) values ('Sambar', 'gravy', 'veg')
       returning id, track_variety, dietary_flags`
    );
    expect(dish.rows[0].track_variety).toBe(true); // default
    expect(dish.rows[0].dietary_flags).toEqual([]);

    const ing = await db.query(
      `insert into ingredients (canonical_name) values ('Toor dal') returning id, is_staple`
    );
    expect(ing.rows[0].is_staple).toBe(false); // default

    await db.query(
      `insert into dish_ingredients (dish_id, ingredient_id) values ($1, $2)`,
      [dish.rows[0].id, ing.rows[0].id]
    );

    // duplicate canonical_name rejected
    await expect(
      db.query(`insert into ingredients (canonical_name) values ('Toor dal')`)
    ).rejects.toThrow();

    // dish_ingredients FK enforced
    await expect(
      db.query(`insert into dish_ingredients (dish_id, ingredient_id) values (gen_random_uuid(), $1)`, [
        ing.rows[0].id,
      ])
    ).rejects.toThrow();

    // ingredient_aliases FK cascade: deleting the ingredient removes the alias
    await db.query(`insert into ingredient_aliases (alias_text, ingredient_id) values ('dal', $1)`, [
      ing.rows[0].id,
    ]);
    await db.query(`delete from ingredients where id = $1`, [ing.rows[0].id]);
    const aliasCount = await db.query(`select count(*)::int as n from ingredient_aliases`);
    expect(aliasCount.rows[0].n).toBe(0);
  });
});

describe('MP-008 — user profile and favorites schema', () => {
  it('matches the documented model: planning_mode default, check constraints, FK to auth.users', async () => {
    const profile = await db.query(
      `insert into user_profiles (id, grocery_day) values ($1, 'saturday')
       returning planning_mode, dinner_style, timezone`,
      [USER_A]
    );
    expect(profile.rows[0].planning_mode).toBe('suggestion'); // default per functional spec §2/§7
    expect(profile.rows[0].dinner_style).toBe('rice');
    expect(profile.rows[0].timezone).toBe('Asia/Kolkata');

    // invalid planning_mode rejected
    await expect(
      db.query(
        `insert into user_profiles (id, grocery_day, planning_mode) values (gen_random_uuid(), 'monday', 'bogus')`
      )
    ).rejects.toThrow();

    // FK to auth.users enforced
    await expect(
      db.query(`insert into user_profiles (id, grocery_day) values (gen_random_uuid(), 'monday')`)
    ).rejects.toThrow();
  });

  it('enforces favorites uniqueness — a user cannot favorite the same dish twice', async () => {
    const dish = await db.query(
      `insert into dishes (name, item_type, veg_or_nonveg) values ('Rasam', 'gravy', 'veg') returning id`
    );
    await db.query(`insert into user_profiles (id, grocery_day) values ($1, 'saturday')`, [USER_A]);
    await db.query(`insert into user_favorite_dishes (user_id, dish_id) values ($1, $2)`, [
      USER_A,
      dish.rows[0].id,
    ]);
    await expect(
      db.query(`insert into user_favorite_dishes (user_id, dish_id) values ($1, $2)`, [
        USER_A,
        dish.rows[0].id,
      ])
    ).rejects.toThrow();
  });
});

describe('MP-009 — meal plan schema', () => {
  it('supports the six daily slots and make_extra, with a unique user/date/slot constraint', async () => {
    await db.query(`insert into user_profiles (id, grocery_day) values ($1, 'saturday')`, [USER_A]);
    const dish = await db.query(
      `insert into dishes (name, item_type, veg_or_nonveg) values ('Idli', 'tiffin', 'veg') returning id`
    );

    for (const slot of ['morning', 'afternoon', 'night', 'snack_1', 'snack_2', 'snack_3']) {
      const plan = await db.query(
        `insert into meal_plans (user_id, plan_date, slot) values ($1, '2026-08-24', $2) returning id`,
        [USER_A, slot]
      );
      expect(plan.rows[0].id).toBeTruthy();
    }

    // invalid slot rejected
    await expect(
      db.query(`insert into meal_plans (user_id, plan_date, slot) values ($1, '2026-08-25', 'brunch')`, [
        USER_A,
      ])
    ).rejects.toThrow();

    // duplicate (user, date, slot) rejected
    await expect(
      db.query(`insert into meal_plans (user_id, plan_date, slot) values ($1, '2026-08-24', 'morning')`, [
        USER_A,
      ])
    ).rejects.toThrow();

    const plan = await db.query(
      `select id from meal_plans where user_id = $1 and plan_date = '2026-08-24' and slot = 'morning'`,
      [USER_A]
    );
    const item = await db.query(
      `insert into plan_items (plan_id, item_type, dish_id) values ($1, 'tiffin', $2) returning make_extra`,
      [plan.rows[0].id, dish.rows[0].id]
    );
    expect(item.rows[0].make_extra).toBe(false); // default
  });
});

describe('MP-010 — generation and notification tables', () => {
  it('idempotency: unique(user_id, week_start) on generation_jobs prevents duplicate jobs', async () => {
    await db.query(`insert into user_profiles (id, grocery_day) values ($1, 'saturday')`, [USER_A]);
    await db.query(`insert into generation_jobs (user_id, week_start) values ($1, '2026-08-24')`, [
      USER_A,
    ]);
    await expect(
      db.query(`insert into generation_jobs (user_id, week_start) values ($1, '2026-08-24')`, [USER_A])
    ).rejects.toThrow();

    await expect(
      db.query(`insert into generation_jobs (user_id, week_start, status) values ($1, '2026-08-31', 'bogus')`, [
        USER_A,
      ])
    ).rejects.toThrow();
  });

  it('idempotency: unique(user_id, notification_type, target_date) on notification_log prevents duplicate sends', async () => {
    await db.query(`insert into user_profiles (id, grocery_day) values ($1, 'saturday')`, [USER_A]);
    await db.query(
      `insert into notification_log (user_id, notification_type, target_date) values ($1, 'daily_reminder', '2026-08-24')`,
      [USER_A]
    );
    await expect(
      db.query(
        `insert into notification_log (user_id, notification_type, target_date) values ($1, 'daily_reminder', '2026-08-24')`,
        [USER_A]
      )
    ).rejects.toThrow();
  });
});

describe('MP-011 — ingredient availability and grocery snapshot schema', () => {
  it('stores weekly availability and frozen snapshots per user/week (CRUD)', async () => {
    await db.query(`insert into user_profiles (id, grocery_day) values ($1, 'saturday')`, [USER_A]);
    const ing = await db.query(
      `insert into ingredients (canonical_name) values ('Drumstick') returning id`
    );

    await db.query(
      `insert into available_ingredients (user_id, week_start, ingredient_id) values ($1, '2026-08-24', $2)`,
      [USER_A, ing.rows[0].id]
    );
    const read = await db.query(`select * from available_ingredients where user_id = $1`, [USER_A]);
    expect(read.rows).toHaveLength(1);

    await db.query(
      `delete from available_ingredients where user_id = $1 and week_start = '2026-08-24' and ingredient_id = $2`,
      [USER_A, ing.rows[0].id]
    );
    const afterDelete = await db.query(`select * from available_ingredients where user_id = $1`, [
      USER_A,
    ]);
    expect(afterDelete.rows).toHaveLength(0);

    await db.query(
      `insert into grocery_list_snapshot (user_id, week_start, ingredients) values ($1, '2026-08-24', $2)`,
      [USER_A, JSON.stringify([{ ingredient_id: ing.rows[0].id, name: 'Drumstick' }])]
    );
    // primary key (user_id, week_start) — duplicate snapshot for the same week rejected
    await expect(
      db.query(
        `insert into grocery_list_snapshot (user_id, week_start, ingredients) values ($1, '2026-08-24', '[]')`,
        [USER_A]
      )
    ).rejects.toThrow();
  });
});
