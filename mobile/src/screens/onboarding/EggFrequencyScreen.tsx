import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useOnboarding } from '../../contexts/OnboardingContext';
import {
  DAY_LABELS,
  DAY_NAMES,
  type DayName,
  type EggFrequency,
} from '../../lib/onboardingVocabulary';
import type { OnboardingStackParamList } from '../../navigation/types';
import { spacing } from '../../theme/tokens';
import { OnboardingLayout, SelectableOption } from './OnboardingLayout';

const OPTIONS: { value: EggFrequency; label: string }[] = [
  { value: 'any', label: 'Any day' },
  { value: 'nonveg_days', label: 'Only non-veg days' },
  { value: 'specific', label: 'Specific days' },
  { value: 'never', label: 'Never' },
];

// Q4 — reachable from both the Eggetarian and Non-vegetarian branches (never for Vegetarian, per
// DietTypeScreen's navigation). "Only non-veg days" is offered on both branches per Pratheep's
// decision this phase, even though for Eggetarian it resolves to zero egg-permitted days
// server-side (Eggetarian never has a meat quota to anchor "non-veg day" to) — not a bug, a
// documented quirk of the underlying data model (see generation_context.py's egg_permitted_dates).
export function EggFrequencyScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, 'EggFrequency'>>();
  const { draft, updateDraft } = useOnboarding();
  const [selected, setSelected] = useState<EggFrequency | null>(draft.eggFrequency);
  const [days, setDays] = useState<DayName[]>(draft.eggDayPattern);

  const toggleDay = (day: DayName) => {
    setDays((current) =>
      current.includes(day) ? current.filter((d) => d !== day) : [...current, day],
    );
  };

  const canContinue = selected !== null && (selected !== 'specific' || days.length > 0);

  const handleContinue = () => {
    if (!selected) {
      return;
    }
    updateDraft({
      eggFrequency: selected,
      eggDayPattern: selected === 'specific' ? days : [],
    });
    navigation.navigate('Allergies');
  };

  return (
    <OnboardingLayout
      kicker="4 of 7"
      title="How often can we include eggs?"
      canContinue={canContinue}
      onContinue={handleContinue}
      testIdPrefix="onboarding-egg-frequency"
    >
      {OPTIONS.map((option) => (
        <SelectableOption
          key={option.value}
          label={option.label}
          selected={selected === option.value}
          onPress={() => setSelected(option.value)}
          testID={`onboarding-egg-frequency-${option.value}`}
        />
      ))}

      {selected === 'specific' ? (
        <View style={styles.dayGrid} testID="onboarding-egg-frequency-picker">
          {DAY_NAMES.map((day) => (
            <SelectableOption
              key={day}
              label={DAY_LABELS[day]}
              selected={days.includes(day)}
              onPress={() => toggleDay(day)}
              testID={`onboarding-egg-frequency-day-${day}`}
            />
          ))}
        </View>
      ) : null}
    </OnboardingLayout>
  );
}

const styles = StyleSheet.create({
  dayGrid: {
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
});
