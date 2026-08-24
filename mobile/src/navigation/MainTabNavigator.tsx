import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { DayReviewEditScreen } from '../screens/DayReviewEditScreen';
import { PlaceholderScreen } from '../screens/PlaceholderScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { WeekPlanScreen } from '../screens/WeekPlanScreen';
import type {
  GroceryStackParamList,
  MainTabParamList,
  PlanStackParamList,
  SettingsStackParamList,
} from './types';

const Tab = createBottomTabNavigator<MainTabParamList>();
const PlanStack = createNativeStackNavigator<PlanStackParamList>();
const GroceryStack = createNativeStackNavigator<GroceryStackParamList>();
const SettingsStack = createNativeStackNavigator<SettingsStackParamList>();

function PlanStackNavigator() {
  return (
    <PlanStack.Navigator>
      <PlanStack.Screen name="WeekPlan" component={WeekPlanScreen} options={{ title: 'Plan' }} />
      <PlanStack.Screen
        name="DayReviewEdit"
        component={DayReviewEditScreen}
        options={{ title: 'Review & edit' }}
      />
    </PlanStack.Navigator>
  );
}

function GroceryListScreen() {
  return (
    <PlaceholderScreen
      title="Grocery list"
      note="Auto-generated weekly list lands in a later phase (M5)."
    />
  );
}

function GroceryStackNavigator() {
  return (
    <GroceryStack.Navigator>
      <GroceryStack.Screen
        name="GroceryList"
        component={GroceryListScreen}
        options={{ title: 'Grocery' }}
      />
    </GroceryStack.Navigator>
  );
}

function SettingsStackNavigator() {
  return (
    <SettingsStack.Navigator>
      <SettingsStack.Screen name="Settings" component={SettingsScreen} />
    </SettingsStack.Navigator>
  );
}

export function MainTabNavigator() {
  return (
    <Tab.Navigator screenOptions={{ headerShown: false }}>
      <Tab.Screen name="Plan" component={PlanStackNavigator} />
      <Tab.Screen name="Grocery" component={GroceryStackNavigator} />
      <Tab.Screen
        name="SettingsTab"
        component={SettingsStackNavigator}
        options={{ title: 'Settings' }}
      />
    </Tab.Navigator>
  );
}
