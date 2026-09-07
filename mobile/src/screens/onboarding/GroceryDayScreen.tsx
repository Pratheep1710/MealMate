import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';

import { useOnboarding } from '../../contexts/OnboardingContext';
import { DAY_LABELS, DAY_NAMES, type DayName } from '../../lib/onboardingVocabulary';
import type { OnboardingStackParamList } from '../../navigation/types';
import { OnboardingLayout, SelectableOption } from './OnboardingLayout';

// Q7 — always shown. Single select, full lowercase day name submitted (not an abbreviation —
// see onboardingVocabulary.ts's note on the day-name format asymmetry this avoids).
export function GroceryDayScreen() {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, 'GroceryDay'>>();
  const { draft, updateDraft } = useOnboarding();
  const [selected, setSelected] = useState<DayName | null>(draft.groceryDay);

  const handleContinue = () => {
    if (!selected) {
      return;
    }
    updateDraft({ groceryDay: selected });
    navigation.navigate('Review');
  };

  return (
    <OnboardingLayout
      kicker="7 of 7"
      title="Which day do you usually buy groceries?"
      canContinue={selected !== null}
      onContinue={handleContinue}
      testIdPrefix="onboarding-grocery-day"
    >
      {DAY_NAMES.map((day) => (
        <SelectableOption
          key={day}
          label={DAY_LABELS[day]}
          selected={selected === day}
          onPress={() => setSelected(day)}
          testID={`onboarding-grocery-day-${day}`}
        />
      ))}
    </OnboardingLayout>
  );
}
