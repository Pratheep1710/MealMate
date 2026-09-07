import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { useOnboarding } from '../../contexts/OnboardingContext';
import { computeFirstPlanStart, formatFirstPlanStart } from '../../lib/firstPlanStart';
import { colors, fonts } from '../../theme/tokens';
import { OnboardingLayout } from './OnboardingLayout';

// Final step. MP-026: displays a concrete first-plan-start date computed from planning_mode +
// grocery_day (never asked directly, per the brief — this only computes and shows it). Submitting
// writes the whole draft in one insert; ProfileContext.refresh() inside submit() is what lets
// RootNavigator swap to the main tab stack on its own, same as the existing sign-up flow.
export function ReviewScreen() {
  const { draft, submit } = useOnboarding();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const today = new Date();
  const startLabel =
    draft.groceryDay && draft.planningMode
      ? formatFirstPlanStart(
          computeFirstPlanStart(today, draft.groceryDay, draft.planningMode),
          today,
        )
      : null;

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    const result = await submit();
    setSubmitting(false);
    if (result.error) {
      setError(result.error);
    }
    // Otherwise onboarding is complete: submit() already refreshed ProfileContext, and
    // RootNavigator swaps to the main tab stack on its own — nothing else to do here.
  };

  return (
    <OnboardingLayout
      kicker="Ready"
      title="You're all set"
      subtitle={
        startLabel
          ? `Your first plan starts ${startLabel === 'Today' ? 'today' : `on ${startLabel}`}.`
          : undefined
      }
      canContinue={true}
      onContinue={handleSubmit}
      continueLabel="Start planning"
      submitting={submitting}
      testIdPrefix="onboarding-review"
      error={error}
    >
      <Text style={styles.note} testID="onboarding-review-start-date">
        {startLabel}
      </Text>
    </OnboardingLayout>
  );
}

const styles = StyleSheet.create({
  note: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
  },
});
