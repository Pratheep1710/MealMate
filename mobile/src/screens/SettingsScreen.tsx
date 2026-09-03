import { useEffect, useState } from 'react';
import { Button, FlatList, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { useSession } from '../contexts/SessionContext';
import { type FavoriteDish, listFavorites, removeFavorite } from '../lib/favorites';

// MP-063: management (view/remove) lives here; adding a favorite happens where a dish is actually
// being looked at (DayReviewEditScreen's swap/add pickers) — this list is the "manage what I've
// already picked" half, not a second way to browse the catalog.
export function SettingsScreen() {
  const { session, signOut } = useSession();
  const userId = session?.user.id ?? null;
  const [favorites, setFavorites] = useState<FavoriteDish[] | null>(null);

  const loadFavorites = () => {
    if (!userId) {
      return;
    }
    listFavorites(userId)
      .then(setFavorites)
      .catch(() => setFavorites([]));
  };

  useEffect(() => {
    loadFavorites();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const handleRemove = async (dishId: string) => {
    if (!userId || !favorites) {
      return;
    }
    const previous = favorites;
    setFavorites(favorites.filter((favorite) => favorite.dish_id !== dishId));
    try {
      await removeFavorite(userId, dishId);
    } catch {
      setFavorites(previous);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Settings</Text>
      {session ? <Text style={styles.email}>{session.user.email}</Text> : null}

      <View style={styles.favoritesSection}>
        <Text style={styles.sectionTitle}>Favorites</Text>
        <Text style={styles.sectionNote}>
          Skip the 10-day repeat rule, but still can&apos;t repeat within the same week.
        </Text>
        {favorites === null && <Text style={styles.email}>Loading…</Text>}
        {favorites?.length === 0 && <Text style={styles.email}>No favorites yet.</Text>}
        <FlatList
          data={favorites ?? []}
          keyExtractor={(item) => item.dish_id}
          testID="favorites-list"
          renderItem={({ item }) => (
            <View style={styles.favoriteRow}>
              <Text style={styles.favoriteName}>{item.name}</Text>
              <TouchableOpacity
                onPress={() => handleRemove(item.dish_id)}
                testID={`remove-favorite-${item.dish_id}`}
              >
                <Text style={styles.removeLabel}>Remove</Text>
              </TouchableOpacity>
            </View>
          )}
        />
      </View>

      <Button title="Sign out" onPress={signOut} testID="sign-out" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    gap: 12,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
  },
  email: {
    color: '#666',
  },
  favoritesSection: {
    gap: 6,
    marginVertical: 16,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '600',
  },
  sectionNote: {
    fontSize: 12,
    color: '#888',
  },
  favoriteRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: '#eee',
  },
  favoriteName: {
    fontSize: 14,
  },
  removeLabel: {
    fontSize: 13,
    color: '#888',
  },
});
