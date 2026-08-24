import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Button, StyleSheet, Text, View } from 'react-native';

import type { PlanStackParamList } from '../navigation/types';

export function WeekPlanScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<PlanStackParamList, 'WeekPlan'>>();

  return (
    <View style={styles.container}>
      <Text style={styles.title}>This week&apos;s plan</Text>
      <Text style={styles.note}>Generation and weekly view land in a later phase (M4/M5).</Text>
      <Button
        title="Open a day"
        onPress={() => navigation.navigate('DayReviewEdit', { planDate: '2026-08-24' })}
        testID="open-day-review-edit"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    gap: 12,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
  },
  note: {
    color: '#666',
    textAlign: 'center',
  },
});
