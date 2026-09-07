import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { useOnboarding } from '../../contexts/OnboardingContext';
import type { OnboardingStackParamList } from '../../navigation/types';
import { colors, fonts, spacing } from '../../theme/tokens';
import { OnboardingLayout, SelectableOption } from './OnboardingLayout';

type Mode = 'suggestion' | 'reserves';

// Q6 — always shown, always its own dedicated screen (never a quick toggle in a list), per the
// brief: this is the one irreversible choice in the whole flow. `'suggestion'`/`'reserves'` are
// internal names (MP-025 AC) and must never render as text anywhere on this screen, in any log
// line, or in any error message reachable from the client — copy below is plain-language only.
export function PlanningModeScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, 'PlanningMode'>>();
  const { draft, updateDraft } = useOnboarding();
  const [selected, setSelected] = useState<Mode | null>(draft.planningMode);

  const handleContinue = () => {
    if (!selected) {
      return;
    }
    updateDraft({ planningMode: selected });
    navigation.navigate('GroceryDay');
  };

  return (
    <OnboardingLayout
      kicker="6 of 7"
      title="How should we plan your week?"
      canContinue={selected !== null}
      onContinue={handleContinue}
      testIdPrefix="onboarding-planning-mode"
    >
      <SelectableOption
        label="Plan meals, then give me a shopping list"
        description="We'll build your week and hand you a list to shop from."
        selected={selected === 'suggestion'}
        onPress={() => setSelected('suggestion')}
        testID="onboarding-planning-mode-suggestion"
      />
      <SelectableOption
        label="I'll tell you what I have, plan around it"
        description="You check off what's in your kitchen each week, and we plan around that."
        selected={selected === 'reserves'}
        onPress={() => setSelected('reserves')}
        testID="onboarding-planning-mode-reserves"
      />
      <Text style={styles.notice} testID="onboarding-planning-mode-irreversibility-notice">
        You won&apos;t be able to change this yourself later — choose the one that fits how you
        actually shop.
      </Text>
    </OnboardingLayout>
  );
}

const styles = StyleSheet.create({
  notice: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    lineHeight: 18,
    color: colors.textMuted,
    marginTop: spacing.sm,
  },
});
