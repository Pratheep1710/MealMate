import { StyleSheet, Text, View } from 'react-native';

// Shared shell for screens whose content lands in a later phase (MP-024 onboarding questions,
// M3/M5 plan/grocery/settings UI) — MP-022's job this phase is the route existing and being
// reachable, not the feature behind it.
export function PlaceholderScreen({ title, note }: { title: string; note?: string }) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
      {note ? <Text style={styles.note}>{note}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    gap: 8,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
  },
  note: {
    color: '#666',
    textAlign: 'center',
  },
});
