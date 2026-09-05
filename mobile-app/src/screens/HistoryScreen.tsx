import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { HistoryStackParamList } from '../navigation/RootNavigator';
import { colors, spacing, radii, type } from '../theme';
import { fetchRuns } from '../api/client';
import { RunSummary } from '../api/types';
import { parseSqliteUtc } from '../utils/formatDate';

type Props = NativeStackScreenProps<HistoryStackParamList, 'HistoryList'>;

const DECISION_COLOR: Record<string, string> = {
  ALLOW: colors.allow,
  BLOCK: colors.block,
  REVALIDATE: colors.revalidate,
};

export default function HistoryScreen({ navigation }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRuns(await fetchRuns());
    } catch {
      // best-effort; leave list as-is on failure
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Text style={styles.header}>History</Text>
      <FlatList
        data={runs}
        keyExtractor={(r) => r.run_id}
        contentContainerStyle={{ padding: spacing.lg }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.primary} />}
        ListEmptyComponent={
          <Text style={styles.empty}>No runs yet - ask the agent to buy something first.</Text>
        }
        renderItem={({ item }) => (
          <Pressable style={styles.row} onPress={() => navigation.navigate('RunDetail', { runId: item.run_id })}>
            <View style={styles.rowLeft}>
              <Text style={styles.product}>{item.product_id}</Text>
              <Text style={styles.date}>{parseSqliteUtc(item.created_at).toLocaleString()}</Text>
            </View>
            <View style={styles.rowRight}>
              {item.decision && (
                <View style={[styles.badge, { backgroundColor: `${DECISION_COLOR[item.decision]}22` }]}>
                  <Text style={[styles.badgeText, { color: DECISION_COLOR[item.decision] }]}>{item.decision}</Text>
                </View>
              )}
              <Ionicons name="chevron-forward" size={18} color={colors.textSecondary} />
            </View>
          </Pressable>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { ...type.h2, color: colors.textPrimary, padding: spacing.lg, paddingBottom: 0 },
  empty: { ...type.body, color: colors.textSecondary, textAlign: 'center', marginTop: spacing.xl },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.white,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  rowLeft: { flex: 1 },
  product: { ...type.bodyMedium, color: colors.textPrimary },
  date: { ...type.caption, color: colors.textSecondary, marginTop: 2 },
  rowRight: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radii.pill },
  badgeText: { ...type.caption, fontFamily: 'Inter_600SemiBold' },
});
