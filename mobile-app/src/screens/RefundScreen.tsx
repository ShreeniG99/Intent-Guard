import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AgentStackParamList } from '../navigation/RootNavigator';
import { colors, spacing, radii, type } from '../theme';
import GradientButton from '../components/GradientButton';

type Props = NativeStackScreenProps<AgentStackParamList, 'Refund'>;

export default function RefundScreen({ route, navigation }: Props) {
  const { reason, product, runId } = route.params;

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.iconCircle}>
        <Ionicons name="arrow-undo" size={44} color={colors.white} />
      </View>
      <Text style={styles.title}>Refunded</Text>
      <Text style={styles.subtitle}>{product}</Text>

      <View style={styles.card}>
        <Text style={styles.cardHeading}>What happened</Text>
        <Text style={styles.explain}>
          Your payment was captured, but a check right after capture found the order no longer matched what you
          originally asked for. Rather than keep money that shouldn't have been taken, it was refunded automatically.
        </Text>
        <View style={styles.divider} />
        <Text style={styles.cardHeading}>Reason</Text>
        {reason.map((r, i) => (
          <Text key={i} style={styles.reasonText}>
            • {r}
          </Text>
        ))}
      </View>

      <Text style={styles.runId}>Run {runId}</Text>
      <GradientButton
        label="Back to Agent"
        onPress={() => navigation.popToTop()}
        borderRadius={0}
        style={{ marginTop: spacing.lg, width: '100%' }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, alignItems: 'center', padding: spacing.xl, paddingTop: spacing.xxl },
  iconCircle: {
    width: 88,
    height: 88,
    borderRadius: radii.pill,
    backgroundColor: colors.refund,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  title: { ...type.h1, color: colors.refund },
  subtitle: { ...type.body, color: colors.textSecondary, marginTop: spacing.xs, marginBottom: spacing.lg },
  card: { width: '100%', backgroundColor: colors.refundBg, borderRadius: radii.lg, padding: spacing.lg },
  cardHeading: { ...type.bodyMedium, fontFamily: 'Inter_600SemiBold', color: colors.textPrimary },
  explain: { ...type.body, color: colors.textPrimary, marginTop: spacing.xs },
  divider: { height: 1, backgroundColor: 'rgba(139,92,246,0.2)', marginVertical: spacing.md },
  reasonText: { ...type.body, color: colors.textPrimary, marginTop: 2 },
  runId: { ...type.caption, color: colors.textSecondary, marginTop: spacing.lg },
});
