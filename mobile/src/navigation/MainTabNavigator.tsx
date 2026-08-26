import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { ListTabIcon, PersonTabIcon, WeekTabIcon } from '../components/icons';
import { usePushRegistration } from '../lib/usePushRegistration';
import { DayReviewEditScreen } from '../screens/DayReviewEditScreen';
import { GroceryListScreen } from '../screens/GroceryListScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { WeekPlanScreen } from '../screens/WeekPlanScreen';
import { colors } from '../theme/tokens';
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
  usePushRegistration();

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.leaf,
        tabBarInactiveTintColor: colors.textFaint,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
      }}
    >
      <Tab.Screen
        name="Plan"
        component={PlanStackNavigator}
        options={{
          title: 'Week',
          tabBarIcon: ({ color, size }) => <WeekTabIcon size={size} color={color} />,
        }}
      />
      <Tab.Screen
        name="Grocery"
        component={GroceryStackNavigator}
        options={{
          title: 'List',
          tabBarIcon: ({ color, size }) => <ListTabIcon size={size} color={color} />,
        }}
      />
      <Tab.Screen
        name="SettingsTab"
        component={SettingsStackNavigator}
        options={{
          title: 'You',
          tabBarIcon: ({ color, size }) => <PersonTabIcon size={size} color={color} />,
        }}
      />
    </Tab.Navigator>
  );
}
