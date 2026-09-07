import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';

import { useOnboarding } from '../../contexts/OnboardingContext';
import { MEAT_TYPE_VALUES, type MeatType } from '../../lib/onboardingVocabulary';
import type { OnboardingStackParamList } from '../../navigation/types';
import { OnboardingLayout, SelectableOption } from './OnboardingLayout';

const LABELS: Record<MeatType, string> = {
  chicken: 'Chicken',
  mutton: 'Mutton',
  fish: 'Fish',
  seafood: 'Seafood',
  other: 'Other',
};

// Q2 — only reachable from DietTypeScreen's Non-vegetarian branch. Multi-select; at least one
// choice is required (an empty selection would mean "no meat preference restriction" server-side,
// which isn't a coherent answer to "which meats do you eat" for someone who just said non-veg).
export function MeatTypesScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, 'MeatTypes'>>();
  const { draft, updateDraft } = useOnboarding();
  const [selected, setSelected] = useState<MeatType[]>(draft.meatTypes);

  const toggle = (value: MeatType) => {
    setSelected((current) =>
      current.includes(value) ? current.filter((v) => v !== value) : [...current, value],
    );
  };

  const handleContinue = () => {
    updateDraft({ meatTypes: selected });
    navigation.navigate('NonvegDays');
  };

  return (
    <OnboardingLayout
      kicker="2 of 7"
      title="Which meats do you eat?"
      subtitle="Select all that apply."
      canContinue={selected.length > 0}
      onContinue={handleContinue}
      testIdPrefix="onboarding-meat-types"
    >
      {MEAT_TYPE_VALUES.map((value) => (
        <SelectableOption
          key={value}
          label={LABELS[value]}
          selected={selected.includes(value)}
          onPress={() => toggle(value)}
          testID={`onboarding-meat-types-${value}`}
        />
      ))}
    </OnboardingLayout>
  );
}
