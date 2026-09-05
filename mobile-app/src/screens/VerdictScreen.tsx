import { useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AgentStackParamList } from '../navigation/RootNavigator';
import { colors, spacing, radii, type } from '../theme';
import { useFirewallSocket } from '../api/useFirewallSocket';
import { AgentStepEvent, CheckoutDecisionEvent } from '../api/types';
import { triggerAgentPayment } from '../api/client';
import GradientButton from '../components/GradientButton';

type Props = NativeStackScreenProps<AgentStackParamList, 'Verdict'>;

const PRESENTATION: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string; bg: string; heading: string }> = {
  ALLOW: { icon: 'shield-checkmark', color: colors.allow, bg: colors.allowBg, heading: 'Verified & Approved' },
  BLOCK: { icon: 'close-circle', color: colors.block, bg: colors.blockBg, heading: 'Blocked' },
  REVALIDATE: { icon: 'refresh-circle', color: colors.revalidate, bg: colors.revalidateBg, heading: 'Re-checking...' },
};

export default function VerdictScreen({ route, navigation }: Props) {
  const { runId, product } = route.params;
  const { events } = useFirewallSocket(runId);
  const decisions = events.filter((e): e is CheckoutDecisionEvent => e.event === 'checkout_decision');
  const latest = decisions[decisions.length - 1];
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const confirmAndPay = async () => {
    if (!latest?.razorpay_order_id || starting) return;
    setStarting(true);
    setStartError(null);
    try {
      await triggerAgentPayment(runId);
      const stepsBeforePayment = events.filter((e): e is AgentStepEvent => e.event === 'agent_step').length;
      navigation.replace('Payment', { runId, orderId: latest.razorpay_order_id, product, stepsBeforePayment });
    } catch (e: any) {
      setStarting(false);
      setStartError(e?.message ?? 'Could not start the payment agent. Try again.');
    }
  };

  if (!latest) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator color={colors.primary} size="large" />
      </SafeAreaView>
    );
  }

  const p = PRESENTATION[latest.decision];
  const wasRevalidated = decisions.length > 1;

  return (
    <SafeAreaView style={styles.container}>
      <View style={[styles.iconCircle, { backgroundColor: p.bg }]}>
        <Ionicons name={p.icon} size={56} color={p.color} />
      </View>
      <Text style={[styles.heading, { color: p.color }]}>{p.heading}</Text>
      <Text style={styles.product}>{product}</Text>

      {latest.decision === 'REVALIDATE' && (
        <View style={styles.revalidateBlock}>
          <ActivityIndicator color={colors.revalidate} />
          <Text style={styles.revalidateText}>
            Something on the page needs a closer look. Re-verifying against your original request...
          </Text>
        </View>
      )}

      {latest.decision === 'BLOCK' && (
        <View style={[styles.reasonCard, { backgroundColor: p.bg }]}>
          <Text style={styles.reasonLabel}>Why this was blocked</Text>
          {(latest.hard_block_reasons ?? []).map((r, i) => (
            <Text key={i} style={styles.reasonText}>
              • {r}
            </Text>
          ))}
          {(!latest.hard_block_reasons || latest.hard_block_reasons.length === 0) && (
            <Text style={styles.reasonText}>Risk score {latest.risk_score.toFixed(1)} exceeded the safe threshold.</Text>
          )}
        </View>
      )}

      {latest.decision === 'ALLOW' && (
        <>
          {wasRevalidated && <Text style={styles.recoveredNote}>Re-verified successfully.</Text>}
          <View style={styles.reasonCard}>
            <Text style={styles.reasonLabel}>Ready to pay</Text>
            <Text style={styles.reasonText}>
              The listing matched what you asked for. Confirm to let the agent complete the payment securely.
            </Text>
          </View>
          <GradientButton
            label={starting ? 'Starting...' : 'Confirm and Pay'}
            onPress={confirmAndPay}
            loading={starting}
            style={{ marginTop: spacing.xl, width: '100%' }}
          />
          {startError && <Text style={styles.errorText}>{startError}</Text>}
        </>
      )}

      {latest.decision === 'BLOCK' && (
        <GradientButton
          label="Back to Agent"
          onPress={() => navigation.popToTop()}
          borderRadius={0}
          style={{ marginTop: spacing.xl, width: '100%' }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, alignItems: 'center', padding: spacing.xl, paddingTop: spacing.xxl },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background },
  iconCircle: { width: 110, height: 110, borderRadius: radii.pill, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.lg },
  heading: { ...type.h1, textAlign: 'center' },
  product: { ...type.body, color: colors.textSecondary, marginTop: spacing.xs, marginBottom: spacing.lg },
  revalidateBlock: { alignItems: 'center', gap: spacing.sm, marginTop: spacing.md },
  revalidateText: { ...type.body, color: colors.textSecondary, textAlign: 'center', paddingHorizontal: spacing.lg },
  reasonCard: { width: '100%', borderRadius: radii.lg, padding: spacing.lg, marginTop: spacing.md, backgroundColor: colors.greyLight },
  reasonLabel: { ...type.bodyMedium, fontFamily: 'Inter_600SemiBold', color: colors.textPrimary, marginBottom: spacing.xs },
  reasonText: { ...type.body, color: colors.textPrimary, marginTop: 2 },
  recoveredNote: { ...type.body, color: colors.allow, marginTop: spacing.md },
  errorText: { ...type.caption, color: colors.block, textAlign: 'center', marginTop: spacing.sm },
});
