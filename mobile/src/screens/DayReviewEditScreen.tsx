import { useRoute, type RouteProp } from '@react-navigation/native';

import type { PlanStackParamList } from '../navigation/types';
import { PlaceholderScreen } from './PlaceholderScreen';

export function DayReviewEditScreen() {
  const { params } = useRoute<RouteProp<PlanStackParamList, 'DayReviewEdit'>>();

  return (
    <PlaceholderScreen
      title={`Review & edit — ${params.planDate}`}
      note="Item-level swap/add/remove lands in a later phase (M5)."
    />
  );
}
