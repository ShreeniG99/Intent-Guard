import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { HistoryStackParamList } from '../navigation/RootNavigator';
import { colors, spacing, type } from '../theme';
import { fetchRunDetail } from '../api/client';
import { RunDetail } from '../api/types';
import Timeline from '../components/Timeline';
import { parseSqliteUtc } from '../utils/formatDate';

type Props = NativeStackScreenProps<HistoryStackParamList, 'RunDetail'>;

const DECISION_COLOR: Record<string, string> = {
  ALLOW: colors.allow,
  BLOCK: colors.block,
  REVALIDATE: colors.revalidate,
};

export default function RunDetailScreen({ route, navigation }: Props) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRunDetail(route.params.runId)
      .then(setDetail)
      .finally(() => setLoading(false));
  }, [route.params.runId]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={12}>
          <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>{detail?.product_id ?? 'Run detail'}</Text>
        <View style={{ width: 22 }} />
      </View>

      {loading && (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      )}

      {detail && (
        <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
          <View style={styles.summaryRow}>
            {detail.decision && (
              <Text style={[styles.decision, { color: DECISION_COLOR[detail.decision] }]}>{detail.decision}</Text>
            )}
            {detail.payment_status && <Text style={styles.paymentStatus}>· {detail.payment_status}</Text>}
          </View>
          <Text style={styles.date}>{parseSqliteUtc(detail.created_at).toLocaleString()}</Text>
          <View style={styles.divider} />
          <Timeline steps={detail.steps} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing.lg,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { ...type.h3, color: colors.textPrimary },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  summaryRow: { flexDirection: 'row', alignItems: 'baseline', gap: spacing.xs },
  decision: { ...type.h2 },
  paymentStatus: { ...type.body, color: colors.textSecondary },
  date: { ...type.caption, color: colors.textSecondary, marginTop: 2 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
});
