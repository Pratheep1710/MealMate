import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';

import { useOnboarding } from '../../contexts/OnboardingContext';
import type { DietType } from '../../lib/onboardingVocabulary';
import type { OnboardingStackParamList } from '../../navigation/types';
import { OnboardingLayout, SelectableOption } from './OnboardingLayout';

const OPTIONS: { value: DietType; label: string }[] = [
  { value: 'vegetarian', label: 'Vegetarian' },
  { value: 'eggetarian', label: 'Eggetarian' },
  { value: 'nonvegetarian', label: 'Non-vegetarian' },
];

// Q1 — always the first onboarding question. Which screen Continue navigates to *is* the
// branching logic (MP-024 AC: Q2/Q3/Q4 must be genuinely unreachable, not just hidden by CSS) —
// a Vegetarian selection here never mounts MeatTypes/NonvegDays/EggFrequency at all.
export function DietTypeScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, 'DietType'>>();
  const { draft, updateDraft } = useOnboarding();
  const [selected, setSelected] = useState<DietType | null>(draft.dietType);

  const handleContinue = () => {
    if (!selected) {
      return;
    }
    updateDraft({ dietType: selected });
    if (selected === 'nonvegetarian') {
      navigation.navigate('MeatTypes');
    } else if (selected === 'eggetarian') {
      navigation.navigate('EggFrequency');
    } else {
      navigation.navigate('Allergies');
    }
  };

  return (
    <OnboardingLayout
      kicker="1 of 7"
      title="What type of food do you eat?"
      canContinue={selected !== null}
      onContinue={handleContinue}
      testIdPrefix="onboarding-diet-type"
    >
      {OPTIONS.map((option) => (
        <SelectableOption
          key={option.value}
          label={option.label}
          selected={selected === option.value}
          onPress={() => setSelected(option.value)}
          testID={`onboarding-diet-type-${option.value}`}
        />
      ))}
    </OnboardingLayout>
  );
}
