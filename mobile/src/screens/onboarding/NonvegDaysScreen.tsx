import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { useOnboarding } from '../../contexts/OnboardingContext';
import { DAY_LABELS, DAY_NAMES, type DayName } from '../../lib/onboardingVocabulary';
import type { OnboardingStackParamList } from '../../navigation/types';
import { colors, fonts, radii, spacing } from '../../theme/tokens';
import { OnboardingLayout, SelectableOption } from './OnboardingLayout';

type DaysMode = 'no_preference' | 'specific';

// Q3 — only reachable from the Non-vegetarian branch. Defaults to "No preference — you decide"
// (the lighter-tap option, per the brief) rather than forcing a 7-day picker as the only path; a
// day-picker only reveals if the user actively asks for one, and its selection count must match
// the stepper (mirrors UserProfile's own nonveg_days_per_week/nonveg_day_pattern invariant).
export function NonvegDaysScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, 'NonvegDays'>>();
  const { draft, updateDraft } = useOnboarding();
  const [count, setCount] = useState(draft.nonvegDaysPerWeek ?? 3);
  const [mode, setMode] = useState<DaysMode>(
    draft.nonvegDayPattern.length > 0 ? 'specific' : 'no_preference',
  );
  const [days, setDays] = useState<DayName[]>(draft.nonvegDayPattern);

  const toggleDay = (day: DayName) => {
    setDays((current) =>
      current.includes(day) ? current.filter((d) => d !== day) : [...current, day],
    );
  };

  const canContinue = mode === 'no_preference' || days.length === count;

  const handleContinue = () => {
    updateDraft({
      nonvegDaysPerWeek: count,
      nonvegDayPattern: mode === 'specific' ? days : [],
    });
    navigation.navigate('EggFrequency');
  };

  return (
    <OnboardingLayout
      kicker="3 of 7"
      title="Non-veg days per week?"
      canContinue={canContinue}
      onContinue={handleContinue}
      testIdPrefix="onboarding-nonveg-days"
    >
      <View style={styles.stepper}>
        <TouchableOpacity
          style={styles.stepperButton}
          onPress={() => setCount((c) => Math.max(0, c - 1))}
          testID="onboarding-nonveg-days-decrement"
        >
          <Text style={styles.stepperButtonLabel}>−</Text>
        </TouchableOpacity>
        <Text style={styles.stepperValue} testID="onboarding-nonveg-days-count">
          {count}
        </Text>
        <TouchableOpacity
          style={styles.stepperButton}
          onPress={() => setCount((c) => Math.min(7, c + 1))}
          testID="onboarding-nonveg-days-increment"
        >
          <Text style={styles.stepperButtonLabel}>+</Text>
        </TouchableOpacity>
      </View>

      <SelectableOption
        label="No preference — you decide"
        selected={mode === 'no_preference'}
        onPress={() => setMode('no_preference')}
        testID="onboarding-nonveg-days-no-preference"
      />
      <SelectableOption
        label="Let me pick the days"
        selected={mode === 'specific'}
        onPress={() => setMode('specific')}
        testID="onboarding-nonveg-days-pick-specific"
      />

      {mode === 'specific' ? (
        <View style={styles.dayGrid} testID="onboarding-nonveg-days-picker">
          {DAY_NAMES.map((day) => (
            <SelectableOption
              key={day}
              label={DAY_LABELS[day]}
              selected={days.includes(day)}
              onPress={() => toggleDay(day)}
              testID={`onboarding-nonveg-days-day-${day}`}
            />
          ))}
          <Text style={styles.hint}>
            {days.length}/{count} days selected
          </Text>
        </View>
      ) : null}
    </OnboardingLayout>
  );
}

const styles = StyleSheet.create({
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.lg,
    marginBottom: spacing.md,
  },
  stepperButton: {
    width: 48,
    height: 48,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  stepperButtonLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 22,
    color: colors.textPrimary,
  },
  stepperValue: {
    fontFamily: fonts.displayLight,
    fontSize: 36,
    color: colors.textPrimary,
    minWidth: 40,
    textAlign: 'center',
  },
  dayGrid: {
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  hint: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
  },
});
