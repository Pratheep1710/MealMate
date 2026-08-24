import { useState } from 'react';
import { Button, StyleSheet, Text, TextInput, View } from 'react-native';

import { useSession } from '../contexts/SessionContext';

export function SignInScreen() {
  const { signInWithPassword } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSignIn = async () => {
    setSubmitting(true);
    setError(null);
    const { error: signInError } = await signInWithPassword(email, password);
    setSubmitting(false);
    if (signInError) {
      setError(signInError);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Meal Planner</Text>
      <TextInput
        style={styles.input}
        placeholder="Email"
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
        testID="sign-in-email"
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
        testID="sign-in-password"
      />
      {error ? (
        <Text style={styles.error} testID="sign-in-error">
          {error}
        </Text>
      ) : null}
      <Button
        title={submitting ? 'Signing in…' : 'Sign in'}
        onPress={handleSignIn}
        disabled={submitting || !email || !password}
        testID="sign-in-submit"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: 24,
    gap: 12,
  },
  title: {
    fontSize: 24,
    fontWeight: '600',
    marginBottom: 12,
    textAlign: 'center',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
    padding: 12,
  },
  error: {
    color: '#b00020',
  },
});
