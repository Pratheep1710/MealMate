import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { useOnboarding } from '../../contexts/OnboardingContext';
import { DIETARY_FLAG_VALUES, type DietaryFlag } from '../../lib/onboardingVocabulary';
import type { OnboardingStackParamList } from '../../navigation/types';
import { colors, fonts, radii, spacing } from '../../theme/tokens';
import { OnboardingLayout, SelectableOption } from './OnboardingLayout';

const LABELS: Record<DietaryFlag, string> = {
  Nuts: 'Nuts',
  'Milk-Dairy': 'Milk / Dairy',
  Gluten: 'Gluten',
  Egg: 'Egg',
  Seafood: 'Seafood',
  Sesame: 'Sesame',
};

// Q5 — always shown. This is the hard-exclusion vocabulary (matches MP-017/DIETARY_FLAG_VALUES
// exactly, casing included) that generation_eligibility.py and the swap RPCs both independently
// enforce — see backend/tests/test_diet_cross_check.py for the verification that they agree.
//
// "Other" is free text, stored only in allergyOtherText for manual triage — it is never merged
// into `allergies` (the submitted dietary_restrictions array) and so can never reach a generation
// or swap-time LLM call. "None" is a UI-only affordance (clears every other selection); it is not
// itself a submitted value — an empty `allergies` array already means "no restrictions."
export function AllergiesScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, 'Allergies'>>();
  const { draft, updateDraft } = useOnboarding();
  const [selected, setSelected] = useState<DietaryFlag[]>(draft.allergies as DietaryFlag[]);
  const [otherSelected, setOtherSelected] = useState(draft.allergyOtherText.length > 0);
  const [otherText, setOtherText] = useState(draft.allergyOtherText);
  const [noneSelected, setNoneSelected] = useState(
    draft.allergies.length === 0 && draft.allergyOtherText.length === 0,
  );

  const toggle = (flag: DietaryFlag) => {
    setNoneSelected(false);
    setSelected((current) =>
      current.includes(flag) ? current.filter((f) => f !== flag) : [...current, flag],
    );
  };

  const toggleOther = () => {
    setNoneSelected(false);
    setOtherSelected((current) => !current);
  };

  const selectNone = () => {
    setNoneSelected(true);
    setSelected([]);
    setOtherSelected(false);
    setOtherText('');
  };

  const handleContinue = () => {
    updateDraft({
      allergies: selected,
      allergyOtherText: otherSelected ? otherText : '',
    });
    navigation.navigate('PlanningMode');
  };

  return (
    <OnboardingLayout
      kicker="5 of 7"
      title="Allergies or medical dietary restrictions?"
      subtitle="Select all that apply — this always overrides any other preference."
      canContinue={true}
      onContinue={handleContinue}
      testIdPrefix="onboarding-allergies"
    >
      {DIETARY_FLAG_VALUES.map((flag) => (
        <SelectableOption
          key={flag}
          label={LABELS[flag]}
          selected={selected.includes(flag)}
          onPress={() => toggle(flag)}
          testID={`onboarding-allergies-${flag}`}
        />
      ))}
      <SelectableOption
        label="Other"
        selected={otherSelected}
        onPress={toggleOther}
        testID="onboarding-allergies-other"
      />
      {otherSelected ? (
        <View style={styles.otherField}>
          <TextInput
            style={styles.otherInput}
            placeholder="Describe it — we'll follow up before it affects your plan"
            placeholderTextColor={colors.textFaint}
            value={otherText}
            onChangeText={setOtherText}
            testID="onboarding-allergies-other-text"
            multiline
          />
        </View>
      ) : null}
      <SelectableOption
        label="None"
        selected={noneSelected}
        onPress={selectNone}
        testID="onboarding-allergies-none"
      />
    </OnboardingLayout>
  );
}

const styles = StyleSheet.create({
  otherField: {
    marginTop: -spacing.xs,
  },
  otherInput: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontFamily: fonts.bodyRegular,
    fontSize: 15,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
});
