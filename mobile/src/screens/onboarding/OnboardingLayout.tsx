import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

import { colors, fonts, radii, spacing } from '../../theme/tokens';

// Phase 8 (MP-024): shared shell for every onboarding question screen — kicker/title/subtitle
// header, scrollable body for the question's own controls, and a footer Continue button. Mirrors
// SignUpScreen.tsx's layout conventions (theme tokens, no third-party form library) rather than
// introducing a new one for eight near-identical screens.
export function OnboardingLayout({
  kicker,
  title,
  subtitle,
  children,
  canContinue,
  onContinue,
  continueLabel = 'Continue',
  submitting = false,
  testIdPrefix,
  error,
}: {
  kicker: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  canContinue: boolean;
  onContinue: () => void;
  continueLabel?: string;
  submitting?: boolean;
  testIdPrefix: string;
  error?: string | null;
}) {
  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.kicker}>{kicker}</Text>
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        <View style={styles.body}>{children}</View>
        {error ? (
          <Text style={styles.error} testID={`${testIdPrefix}-error`}>
            {error}
          </Text>
        ) : null}
      </ScrollView>
      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.submitButton, !canContinue && styles.submitButtonDisabled]}
          onPress={onContinue}
          disabled={!canContinue || submitting}
          testID={`${testIdPrefix}-continue`}
        >
          {submitting ? (
            <ActivityIndicator color={colors.surface} />
          ) : (
            <Text style={styles.submitLabel}>{continueLabel}</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

// Single- or multi-select option card, used by every question screen that isn't a stepper/toggle.
export function SelectableOption({
  label,
  description,
  selected,
  onPress,
  testID,
}: {
  label: string;
  description?: string;
  selected: boolean;
  onPress: () => void;
  testID: string;
}) {
  return (
    <TouchableOpacity
      style={[styles.option, selected && styles.optionSelected]}
      onPress={onPress}
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ selected }}
    >
      <Text style={[styles.optionLabel, selected && styles.optionLabelSelected]}>{label}</Text>
      {description ? <Text style={styles.optionDescription}>{description}</Text> : null}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.ground,
  },
  content: {
    padding: spacing.xl,
    gap: spacing.sm,
    flexGrow: 1,
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
    fontSize: 30,
    lineHeight: 36,
    color: colors.textPrimary,
  },
  subtitle: {
    fontFamily: fonts.bodyRegular,
    fontSize: 15,
    lineHeight: 21,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  body: {
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  error: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: '#B3441F',
    marginTop: spacing.sm,
  },
  footer: {
    padding: spacing.xl,
    paddingTop: spacing.sm,
  },
  submitButton: {
    minHeight: 56,
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
  option: {
    minHeight: 56,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
    justifyContent: 'center',
    gap: 2,
  },
  optionSelected: {
    borderColor: colors.leaf,
    backgroundColor: colors.accentTintActive,
  },
  optionLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    color: colors.textPrimary,
  },
  optionLabelSelected: {
    color: colors.leaf,
  },
  optionDescription: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: colors.textSecondary,
  },
});
