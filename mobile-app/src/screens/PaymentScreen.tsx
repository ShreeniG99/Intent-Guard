import { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AgentStackParamList } from '../navigation/RootNavigator';
import { colors, spacing, type } from '../theme';
import { useFirewallSocket } from '../api/useFirewallSocket';
import { AgentStepEvent, PaymentCapturedEvent, PaymentRefundedEvent } from '../api/types';
import Timeline from '../components/Timeline';

type Props = NativeStackScreenProps<AgentStackParamList, 'Payment'>;

// The agent completes the REAL Razorpay TEST-mode checkout itself, in its
// own real Chrome tab on the server -- nothing renders inside the app here
// besides its live reasoning feed. Whichever way the checkout is completed
// (this agent, or previously a human via WebView), Razorpay's own handler
// posts to /pay/callback, which auto-triggers capture/refund server-side --
// this screen just watches for that outcome over the same run_id.
export default function PaymentScreen({ route, navigation }: Props) {
  const { runId, product, stepsBeforePayment } = route.params;
  const { events } = useFirewallSocket(runId);
  const moved = useRef(false);

  const paymentSteps = events
    .filter((e): e is AgentStepEvent => e.event === 'agent_step')
    .slice(stepsBeforePayment);

  useEffect(() => {
    if (moved.current) return;
    const captured = events.find((e): e is PaymentCapturedEvent => e.event === 'payment_captured');
    const refunded = events.find((e): e is PaymentRefundedEvent => e.event === 'payment_refunded');
    if (captured) {
      moved.current = true;
      navigation.replace('Receipt', { runId, amount: captured.amount, product });
    } else if (refunded) {
      moved.current = true;
      navigation.replace('Refund', { runId, reason: refunded.reason, product });
    }
  }, [events, navigation, runId, product]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <ActivityIndicator color={colors.primary} />
        <View>
          <Text style={styles.headerTitle}>Agent is completing payment</Text>
          <Text style={styles.headerSubtitle}>{product}</Text>
        </View>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
        {paymentSteps.length === 0 ? (
          <Text style={styles.waiting}>Starting the payment agent...</Text>
        ) : (
          <Timeline steps={paymentSteps} />
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.lg,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { ...type.h3, color: colors.textPrimary },
  headerSubtitle: { ...type.caption, color: colors.textSecondary, marginTop: 2 },
  waiting: { ...type.body, color: colors.textSecondary, textAlign: 'center', marginTop: spacing.xl },
});
