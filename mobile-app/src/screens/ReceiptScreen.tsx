import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AgentStackParamList } from '../navigation/RootNavigator';
import { colors, spacing, radii, type } from '../theme';
import GradientButton from '../components/GradientButton';

type Props = NativeStackScreenProps<AgentStackParamList, 'Receipt'>;

export default function ReceiptScreen({ route, navigation }: Props) {
  const { amount, product, runId } = route.params;
  const now = new Date();

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.iconCircle}>
        <Ionicons name="checkmark" size={48} color={colors.white} />
      </View>
      <Text style={styles.title}>Payment Successful</Text>
      <Text style={styles.timestamp}>
        {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} on{' '}
        {now.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })}
      </Text>

      <View style={styles.card}>
        <View style={styles.row}>
          <Text style={styles.label}>Product</Text>
          <Text style={styles.value}>{product}</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.row}>
          <Text style={styles.label}>Amount</Text>
          <Text style={styles.amount}>₹{amount.toFixed(2)}</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.row}>
          <Text style={styles.label}>Run ID</Text>
          <Text style={styles.valueMono}>{runId}</Text>
        </View>
      </View>

      <GradientButton label="Done" onPress={() => navigation.popToTop()} style={{ marginTop: spacing.xl, width: '100%' }} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, alignItems: 'center', padding: spacing.xl, paddingTop: spacing.xxl },
  iconCircle: {
    width: 88,
    height: 88,
    borderRadius: radii.pill,
    backgroundColor: colors.allow,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  title: { ...type.h1, color: colors.textPrimary },
  timestamp: { ...type.caption, color: colors.textSecondary, marginTop: spacing.xs, marginBottom: spacing.xl },
  card: { width: '100%', backgroundColor: colors.white, borderRadius: radii.lg, padding: spacing.lg },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: spacing.sm },
  divider: { height: 1, backgroundColor: colors.border },
  label: { ...type.body, color: colors.textSecondary },
  value: { ...type.bodyMedium, color: colors.textPrimary },
  valueMono: { ...type.caption, color: colors.textSecondary },
  amount: { ...type.h3, color: colors.allow },
});
