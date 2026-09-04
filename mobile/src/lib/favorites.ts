import { supabase } from './supabase';

// MP-063: user_favorite_dishes already grants full CRUD directly to the owning user (0006's RLS
// policies), so this is a plain client write, not an RPC — the one thing an RLS write can't
// express (the 5-8 cap) is enforced by a DB trigger (supabase/migrations/0018_favorites_cap.sql),
// which fires for this insert path the same as any other, so there's nothing extra to check here.
export type FavoriteDish = { dish_id: string; name: string };

export async function listFavorites(userId: string): Promise<FavoriteDish[]> {
  const { data, error } = await supabase
    .from('user_favorite_dishes')
    .select('dish_id, dishes(name)')
    .eq('user_id', userId);
  if (error) {
    throw error;
  }
  return ((data ?? []) as unknown as { dish_id: string; dishes: { name: string } | null }[]).map(
    (row) => ({ dish_id: row.dish_id, name: row.dishes?.name ?? 'Unknown dish' }),
  );
}

export async function addFavorite(
  userId: string,
  dishId: string,
): Promise<{ capReached: boolean }> {
  const { error } = await supabase
    .from('user_favorite_dishes')
    .insert({ user_id: userId, dish_id: dishId });
  // Postgres check_violation is SQLSTATE 23514 — the trigger's own errcode
  // (0018_favorites_cap.sql), surfaced through PostgREST as this code.
  return { capReached: error?.code === '23514' };
}

export async function removeFavorite(userId: string, dishId: string): Promise<void> {
  const { error } = await supabase
    .from('user_favorite_dishes')
    .delete()
    .eq('user_id', userId)
    .eq('dish_id', dishId);
  if (error) {
    throw error;
  }
}
