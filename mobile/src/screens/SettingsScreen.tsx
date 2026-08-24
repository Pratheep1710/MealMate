import { Button, StyleSheet, Text, View } from 'react-native';

import { useSession } from '../contexts/SessionContext';

export function SettingsScreen() {
  const { session, signOut } = useSession();

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Settings</Text>
      {session ? <Text style={styles.email}>{session.user.email}</Text> : null}
      <Button title="Sign out" onPress={signOut} testID="sign-out" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
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
});
