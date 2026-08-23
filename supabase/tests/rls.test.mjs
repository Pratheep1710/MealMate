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
