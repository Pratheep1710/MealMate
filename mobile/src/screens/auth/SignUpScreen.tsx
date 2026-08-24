import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { useSession } from '../../contexts/SessionContext';
import type { AuthStackParamList } from '../../navigation/types';
import { colors, fonts, radii, spacing } from '../../theme/tokens';

// MP-027/028 design pass, Auth: the real account-creation path this design didn't originally spec
// (it leads with phone/Google) — added because email+password is the only mechanism actually
// wired to Supabase Auth right now. See docs/MP-027-design-pass-scope.md.
export function SignUpScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<AuthStackParamList, 'SignUp'>>();
  const { signUp } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmationSent, setConfirmationSent] = useState(false);

  const canSubmit = !submitting && !!email && password.length >= 6;

  const handleSignUp = async () => {
    setSubmitting(true);
    setError(null);
    const result = await signUp(email, password);
    setSubmitting(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    if (result.needsConfirmation) {
      setConfirmationSent(true);
    }
    // Otherwise the project auto-confirmed: onAuthStateChange already picked up the new session,
    // and RootNavigator will move on from here on its own.
  };

  if (confirmationSent) {
    return (
      <View style={styles.container}>
        <View style={styles.content}>
          <Text style={styles.kicker}>Almost there</Text>
          <Text style={styles.title}>Check your email</Text>
          <Text style={styles.subtitle}>
            We sent a confirmation link to {email}. Come back and sign in once you&apos;ve confirmed
            it.
          </Text>
          <TouchableOpacity
            style={styles.submitButton}
            onPress={() => navigation.navigate('SignIn')}
            testID="sign-up-go-to-sign-in"
          >
            <Text style={styles.submitLabel}>Sign in</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.content}>
        <Text style={styles.kicker}>Getting in</Text>
        <Text style={styles.title}>Create an account</Text>
        <Text style={styles.subtitle}>One email, one password. That&apos;s the whole signup.</Text>

        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Email</Text>
          <TextInput
            style={styles.input}
            placeholder="you@example.com"
            placeholderTextColor={colors.textFaint}
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
            testID="sign-up-email"
          />
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Password</Text>
          <TextInput
            style={styles.input}
            placeholder="At least 6 characters"
            placeholderTextColor={colors.textFaint}
            secureTextEntry
            autoComplete="password-new"
            value={password}
            onChangeText={setPassword}
            testID="sign-up-password"
          />
        </View>

        {error ? (
          <Text style={styles.error} testID="sign-up-error">
            {error}
          </Text>
        ) : null}

        <TouchableOpacity
          style={[styles.submitButton, !canSubmit && styles.submitButtonDisabled]}
          onPress={handleSignUp}
          disabled={!canSubmit}
          testID="sign-up-submit"
        >
          {submitting ? (
            <ActivityIndicator color={colors.surface} />
          ) : (
            <Text style={styles.submitLabel}>Create account</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.signInRow}
          onPress={() => navigation.navigate('SignIn')}
          testID="sign-up-go-to-sign-in"
        >
          <Text style={styles.signInPrompt}>Already set up? </Text>
          <Text style={styles.signInLink}>Sign in</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.ground,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.sm,
  },
  kicker: {
    fontFamily: fonts.bodyRegular,
    fontSize: 11,
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    color: colors.textMuted,
  },
  title: {
    fontFamily: fonts.displayLight,
    fontSize: 34,
    lineHeight: 38,
    color: colors.textPrimary,
  },
  subtitle: {
    fontFamily: fonts.bodyRegular,
    fontSize: 15,
    lineHeight: 21,
    color: colors.textSecondary,
    marginBottom: spacing.lg,
  },
  fieldGroup: {
    gap: 6,
    marginBottom: spacing.sm,
  },
  fieldLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 10,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: colors.textMuted,
  },
  input: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    fontFamily: fonts.bodyRegular,
    fontSize: 16,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
  error: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: '#B3441F',
    marginTop: spacing.xs,
  },
  submitButton: {
    minHeight: 56,
    marginTop: spacing.lg,
    borderRadius: radii.lg,
    backgroundColor: colors.leaf,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitButtonDisabled: {
    backgroundColor: colors.borderStrong,
  },
  submitLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    color: colors.surface,
  },
  signInRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
    marginTop: spacing.sm,
  },
  signInPrompt: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
  },
  signInLink: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.leaf,
    textDecorationLine: 'underline',
  },
});
