import { describe, it, expect, beforeEach } from 'vitest';
import { createTestDb, createAuthUser, asUser, asAnon, asServiceRole, reset, USER_A, USER_B } from './helpers.mjs';

// MP-013: negative multi-tenant authorization tests. Each test actively tries to read/write
// another user's row and asserts denial — a passing happy-path test alone is not sufficient
// evidence per the brief's AC for this task. Own-data access is also asserted where it matters,
// so a broken "allow" policy would fail loudly rather than being masked by an overly strict one.

let db, dishId, planA, planB;

beforeEach(async () => {
  db = await createTestDb();
  await createAuthUser(db, USER_A);
  await createAuthUser(db, USER_B);

  await asServiceRole(db);
  await db.query(`insert into user_profiles (id, grocery_day) values ($1, 'saturday')`, [USER_A]);
  await db.query(`insert into user_profiles (id, grocery_day) values ($1, 'sunday')`, [USER_B]);
  const dish = await db.query(
    `insert into dishes (name, item_type, veg_or_nonveg) values ('Idli', 'tiffin', 'veg') returning id`
  );
  dishId = dish.rows[0].id;
  const mpA = await db.query(
    `insert into meal_plans (user_id, plan_date, slot) values ($1, '2026-08-24', 'morning') returning id`,
    [USER_A]
  );
  planA = mpA.rows[0].id;
  const mpB = await db.query(
    `insert into meal_plans (user_id, plan_date, slot) values ($1, '2026-08-24', 'morning') returning id`,
    [USER_B]
  );
  planB = mpB.rows[0].id;
  await db.query(`insert into plan_items (plan_id, item_type, dish_id) values ($1, 'tiffin', $2)`, [
    planA,
    dishId,
  ]);
  await db.query(`insert into plan_items (plan_id, item_type, dish_id) values ($1, 'tiffin', $2)`, [
    planB,
    dishId,
  ]);
  await db.query(
    `insert into notification_log (user_id, notification_type, target_date) values ($1, 'daily_reminder', '2026-08-24')`,
    [USER_A]
  );
  await db.query(`insert into generation_jobs (user_id, week_start) values ($1, '2026-08-24')`, [USER_A]);
  const ing = await db.query(`insert into ingredients (canonical_name) values ('Rice') returning id`);
  await db.query(
    `insert into available_ingredients (user_id, week_start, ingredient_id) values ($1, '2026-08-24', $2)`,
    [USER_A, ing.rows[0].id]
  );
  await db.query(
    `insert into grocery_list_snapshot (user_id, week_start, ingredients) values ($1, '2026-08-24', '[]')`,
    [USER_A]
  );
  await db.query(`insert into user_favorite_dishes (user_id, dish_id) values ($1, $2)`, [USER_A, dishId]);
  await reset(db);
});

describe('user_profiles', () => {
  it('own row: select succeeds', async () => {
    await asUser(db, USER_A);
    const res = await db.query(`select * from user_profiles where id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(1);
  });

  it("other user's row: select returns nothing (denied, not an error)", async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from user_profiles where id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(0);
  });

  it("cannot insert a profile row for another user's id", async () => {
    await asUser(db, USER_B);
    await expect(
      db.query(`insert into user_profiles (id, grocery_day) values ($1, 'monday')`, [USER_A])
    ).rejects.toThrow();
  });

  it('review fix: a user cannot change their own planning_mode, even on their own row (functional spec §2 — immutable after onboarding)', async () => {
    await asUser(db, USER_A);
    await expect(
      db.query(`update user_profiles set planning_mode = 'reserves' where id = $1`, [USER_A])
    ).rejects.toThrow();

    // the column-level revoke must not have taken down updates to columns that ARE allowed
    await db.query(`update user_profiles set dinner_style = 'tiffin' where id = $1`, [USER_A]);
    const check = await db.query(`select dinner_style, planning_mode from user_profiles where id = $1`, [
      USER_A,
    ]);
    expect(check.rows[0].dinner_style).toBe('tiffin');
    expect(check.rows[0].planning_mode).toBe('suggestion'); // unchanged

    // a single statement touching one disallowed column must reject as a whole, not partially apply
    await expect(
      db.query(
        `update user_profiles set dinner_style = 'rice', planning_mode = 'reserves' where id = $1`,
        [USER_A]
      )
    ).rejects.toThrow();
    const afterMixed = await db.query(`select dinner_style from user_profiles where id = $1`, [USER_A]);
    expect(afterMixed.rows[0].dinner_style).toBe('tiffin'); // the rice change did not apply either
  });
});

describe('user_favorite_dishes', () => {
  it("other user's favorites are invisible", async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from user_favorite_dishes where user_id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(0);
  });

  it("cannot insert a favorite row on another user's behalf", async () => {
    await asUser(db, USER_B);
    await expect(
      db.query(`insert into user_favorite_dishes (user_id, dish_id) values ($1, $2)`, [USER_A, dishId])
    ).rejects.toThrow();
  });

  it("cannot delete another user's favorite", async () => {
    await asUser(db, USER_B);
    await db.query(`delete from user_favorite_dishes where user_id = $1`, [USER_A]);
    await reset(db);
    await asServiceRole(db);
    const stillThere = await db.query(`select * from user_favorite_dishes where user_id = $1`, [USER_A]);
    expect(stillThere.rows).toHaveLength(1); // B's delete matched zero rows under RLS, nothing removed
  });
});

describe('meal_plans / plan_items', () => {
  it("other user's plan is invisible", async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from meal_plans where id = $1`, [planA]);
    expect(res.rows).toHaveLength(0);
  });

  it("other user's plan_items are invisible even though item_type/dish_id leak no ownership column", async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from plan_items where plan_id = $1`, [planA]);
    expect(res.rows).toHaveLength(0);
  });

  it("cannot update another user's plan_items", async () => {
    await asUser(db, USER_B);
    const result = await db.query(`update plan_items set make_extra = true where plan_id = $1`, [planA]);
    expect(result.affectedRows ?? 0).toBe(0);

    await reset(db);
    await asServiceRole(db);
    const check = await db.query(`select make_extra from plan_items where plan_id = $1`, [planA]);
    expect(check.rows[0].make_extra).toBe(false);
  });

  it("cannot insert a plan_item into another user's plan", async () => {
    await asUser(db, USER_B);
    await expect(
      db.query(`insert into plan_items (plan_id, item_type, dish_id) values ($1, 'tiffin', $2)`, [
        planA,
        dishId,
      ])
    ).rejects.toThrow();
  });

  it('own plan_items: update succeeds', async () => {
    await asUser(db, USER_A);
    await db.query(`update plan_items set make_extra = true where plan_id = $1`, [planA]);
    const check = await db.query(`select make_extra from plan_items where plan_id = $1`, [planA]);
    expect(check.rows[0].make_extra).toBe(true);
  });

  // MP-061: skip/eating-out toggle write path (0012_meal_plans_skip_toggle_rls.sql).
  it('own meal_plans row: can toggle is_skipped', async () => {
    await asUser(db, USER_A);
    await db.query(`update meal_plans set is_skipped = true where id = $1`, [planA]);
    const check = await db.query(`select is_skipped from meal_plans where id = $1`, [planA]);
    expect(check.rows[0].is_skipped).toBe(true);
  });

  it("cannot toggle another user's is_skipped", async () => {
    await asUser(db, USER_B);
    const result = await db.query(`update meal_plans set is_skipped = true where id = $1`, [planA]);
    expect(result.affectedRows ?? 0).toBe(0);

    await reset(db);
    await asServiceRole(db);
    const check = await db.query(`select is_skipped from meal_plans where id = $1`, [planA]);
    expect(check.rows[0].is_skipped).toBe(false);
  });

  it('the is_skipped grant does not extend to other meal_plans columns', async () => {
    await asUser(db, USER_A);
    await expect(
      db.query(`update meal_plans set slot = 'night' where id = $1`, [planA])
    ).rejects.toThrow();
  });
});

describe('push_tokens — own rows only via SELECT, all writes go through register_push_token', () => {
  it('a user can register their own push token via the RPC', async () => {
    await asUser(db, USER_A);
    await db.query(`select register_push_token('ExponentPushToken[aaa]')`);

    const res = await db.query(`select * from push_tokens where user_id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(1);
    expect(res.rows[0].expo_push_token).toBe('ExponentPushToken[aaa]');
  });

  it("the RPC always registers to the caller's own auth.uid(), never an argument", async () => {
    // register_push_token(text) takes no user id argument at all — auth.uid() is read
    // server-side inside the security-definer function, so there's nothing for a caller to lie
    // about the way a direct `insert ... values (user_id, ...)` would let them.
    await asUser(db, USER_A);
    await db.query(`select register_push_token('ExponentPushToken[bbb]')`);

    const res = await db.query(`select user_id from push_tokens where expo_push_token = 'ExponentPushToken[bbb]'`);
    expect(res.rows[0].user_id).toBe(USER_A);
  });

  it('direct inserts/updates from authenticated are denied — the RPC is the only write path', async () => {
    await asUser(db, USER_A);
    await expect(
      db.query(`insert into push_tokens (user_id, expo_push_token) values ($1, 'ExponentPushToken[ccc]')`, [
        USER_A,
      ])
    ).rejects.toThrow();
  });

  it("other user's token rows are invisible", async () => {
    await asUser(db, USER_A);
    await db.query(`select register_push_token('ExponentPushToken[ddd]')`);
    await reset(db);

    await asUser(db, USER_B);
    const res = await db.query(`select * from push_tokens where user_id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(0);
  });

  it('a device handed off to a different account reassigns the same token row', async () => {
    await asUser(db, USER_A);
    await db.query(`select register_push_token('ExponentPushToken[eee]')`);
    await reset(db);

    // USER_B signs in on the same device and registers the same token value.
    await asUser(db, USER_B);
    await db.query(`select register_push_token('ExponentPushToken[eee]')`);
    await reset(db);

    await asServiceRole(db);
    const res = await db.query(`select user_id from push_tokens where expo_push_token = 'ExponentPushToken[eee]'`);
    expect(res.rows).toHaveLength(1);
    expect(res.rows[0].user_id).toBe(USER_B);
  });

  it('anon cannot call the registration RPC', async () => {
    await asAnon(db);
    await expect(db.query(`select register_push_token('ExponentPushToken[fff]')`)).rejects.toThrow();
  });

  it('a user can unregister their own device token on sign-out', async () => {
    await asUser(db, USER_A);
    await db.query(`select register_push_token('ExponentPushToken[ggg]')`);
    await db.query(`select unregister_push_token('ExponentPushToken[ggg]')`);

    const res = await db.query(`select * from push_tokens where expo_push_token = 'ExponentPushToken[ggg]'`);
    expect(res.rows).toHaveLength(0);
  });

  it("cannot unregister another user's token (account handoff: signing out on device B must not remove device A's still-active registration)", async () => {
    await asUser(db, USER_A);
    await db.query(`select register_push_token('ExponentPushToken[hhh]')`);
    await reset(db);

    await asUser(db, USER_B);
    await db.query(`select unregister_push_token('ExponentPushToken[hhh]')`);
    await reset(db);

    await asServiceRole(db);
    const res = await db.query(`select * from push_tokens where expo_push_token = 'ExponentPushToken[hhh]'`);
    expect(res.rows).toHaveLength(1);
    expect(res.rows[0].user_id).toBe(USER_A);
  });

  it('unregistering an unknown token is a harmless no-op, not an error', async () => {
    await asUser(db, USER_A);
    await expect(
      db.query(`select unregister_push_token('ExponentPushToken[does-not-exist]')`)
    ).resolves.toBeDefined();
  });

  it('anon cannot call the unregister RPC', async () => {
    await asAnon(db);
    await expect(db.query(`select unregister_push_token('ExponentPushToken[fff]')`)).rejects.toThrow();
  });
});

describe('generation_jobs / notification_log — read-only to owner, no cross-user leak', () => {
  it("other user's generation_jobs are invisible", async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from generation_jobs where user_id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(0);
  });

  it('users cannot write generation_jobs directly (service_role only)', async () => {
    await asUser(db, USER_A);
    await expect(
      db.query(`insert into generation_jobs (user_id, week_start) values ($1, '2026-09-01')`, [USER_A])
    ).rejects.toThrow();
  });

  it("other user's notification_log is invisible", async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from notification_log where user_id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(0);
  });
});

describe('available_ingredients — full CRUD for owner, denied cross-user', () => {
  it("other user's availability rows are invisible", async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from available_ingredients where user_id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(0);
  });

  it("cannot delete another user's availability row", async () => {
    await asUser(db, USER_B);
    await db.query(`delete from available_ingredients where user_id = $1`, [USER_A]);
    await reset(db);
    await asServiceRole(db);
    const stillThere = await db.query(`select * from available_ingredients where user_id = $1`, [USER_A]);
    expect(stillThere.rows).toHaveLength(1);
  });
});

describe('grocery_list_snapshot — read-only to owner', () => {
  it("other user's snapshot is invisible", async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from grocery_list_snapshot where user_id = $1`, [USER_A]);
    expect(res.rows).toHaveLength(0);
  });

  it('users cannot write snapshots directly (service_role only)', async () => {
    await asUser(db, USER_B);
    await expect(
      db.query(
        `insert into grocery_list_snapshot (user_id, week_start, ingredients) values ($1, '2026-09-01', '[]')`,
        [USER_B]
      )
    ).rejects.toThrow();
  });
});

describe('catalog tables — readable by any authenticated user, not user-scoped, not writable by them', () => {
  it('dishes are visible to any authenticated user', async () => {
    await asUser(db, USER_B);
    const res = await db.query(`select * from dishes where id = $1`, [dishId]);
    expect(res.rows).toHaveLength(1);
  });

  it('authenticated users cannot write to dishes', async () => {
    await asUser(db, USER_A);
    await expect(
      db.query(`insert into dishes (name, item_type, veg_or_nonveg) values ('Hack', 'tiffin', 'veg')`)
    ).rejects.toThrow();
  });

  it('anon has no access to catalog tables (no grants)', async () => {
    await asAnon(db);
    await expect(db.query(`select * from dishes`)).rejects.toThrow();
  });
});
