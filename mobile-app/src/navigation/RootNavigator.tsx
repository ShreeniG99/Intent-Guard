import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts } from '../theme';

import LoginScreen from '../screens/LoginScreen';
import AgentScreen from '../screens/AgentScreen';
import LiveRunScreen from '../screens/LiveRunScreen';
import VerdictScreen from '../screens/VerdictScreen';
import PaymentScreen from '../screens/PaymentScreen';
import ReceiptScreen from '../screens/ReceiptScreen';
import RefundScreen from '../screens/RefundScreen';
import HistoryScreen from '../screens/HistoryScreen';
import RunDetailScreen from '../screens/RunDetailScreen';

export type AgentStackParamList = {
  AgentChat: undefined;
  LiveRun: { runId: string; product: string };
  Verdict: { runId: string; product: string };
  Payment: { runId: string; orderId: string; product: string; stepsBeforePayment: number };
  Receipt: { runId: string; amount: number; product: string };
  Refund: { runId: string; reason: string[]; product: string };
};

export type HistoryStackParamList = {
  HistoryList: undefined;
  RunDetail: { runId: string };
};

export type RootStackParamList = {
  Login: undefined;
  MainTabs: undefined;
};

const RootStack = createNativeStackNavigator<RootStackParamList>();
const AgentStack = createNativeStackNavigator<AgentStackParamList>();
const HistoryStack = createNativeStackNavigator<HistoryStackParamList>();
const Tab = createBottomTabNavigator();

function AgentStackNavigator() {
  return (
    <AgentStack.Navigator screenOptions={{ headerShown: false }}>
      <AgentStack.Screen name="AgentChat" component={AgentScreen} />
      <AgentStack.Screen name="LiveRun" component={LiveRunScreen} />
      <AgentStack.Screen name="Verdict" component={VerdictScreen} />
      <AgentStack.Screen name="Payment" component={PaymentScreen} />
      <AgentStack.Screen name="Receipt" component={ReceiptScreen} />
      <AgentStack.Screen name="Refund" component={RefundScreen} />
    </AgentStack.Navigator>
  );
}

function HistoryStackNavigator() {
  return (
    <HistoryStack.Navigator screenOptions={{ headerShown: false }}>
      <HistoryStack.Screen name="HistoryList" component={HistoryScreen} />
      <HistoryStack.Screen name="RunDetail" component={RunDetailScreen} />
    </HistoryStack.Navigator>
  );
}

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: { borderTopColor: colors.border, height: 60, paddingBottom: 8, paddingTop: 6 },
        tabBarLabelStyle: { fontFamily: fonts.bodyMedium, fontSize: 12 },
      }}
    >
      <Tab.Screen
        name="Agent"
        component={AgentStackNavigator}
        options={{ tabBarIcon: ({ color, size }) => <Ionicons name="sparkles" size={size} color={color} /> }}
      />
      <Tab.Screen
        name="History"
        component={HistoryStackNavigator}
        options={{ tabBarIcon: ({ color, size }) => <Ionicons name="time-outline" size={size} color={color} /> }}
      />
    </Tab.Navigator>
  );
}

export default function RootNavigator() {
  return (
    <RootStack.Navigator screenOptions={{ headerShown: false }}>
      <RootStack.Screen name="Login" component={LoginScreen} />
      <RootStack.Screen name="MainTabs" component={MainTabs} />
    </RootStack.Navigator>
  );
}
