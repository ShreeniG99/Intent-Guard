import { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Image, ScrollView, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AgentStackParamList } from '../navigation/RootNavigator';
import { colors, spacing, radii, type } from '../theme';
import { useFirewallSocket } from '../api/useFirewallSocket';
import { AgentStepEvent, CheckoutDecisionEvent } from '../api/types';
import Timeline from '../components/Timeline';

type Props = NativeStackScreenProps<AgentStackParamList, 'LiveRun'>;

export default function LiveRunScreen({ route, navigation }: Props) {
  const { runId, product } = route.params;
  const { events, connected } = useFirewallSocket(runId);
  const navigated = useRef(false);

  const steps = events.filter((e): e is AgentStepEvent => e.event === 'agent_step');
  const decision = events.find((e): e is CheckoutDecisionEvent => e.event === 'checkout_decision');
  const latestStep = steps[steps.length - 1];
  const isBrowsing = !decision;

  useEffect(() => {
    if (decision && !navigated.current) {
      navigated.current = true;
      navigation.replace('Verdict', { runId, product });
    }
  }, [decision, navigation, runId, product]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>{product}</Text>
        <View style={styles.statusPill}>
          <View style={[styles.statusDot, { backgroundColor: connected ? colors.allow : colors.grey }]} />
          <Text style={styles.statusText}>{connected ? 'Live' : 'Connecting…'}</Text>
        </View>
      </View>

      {isBrowsing && latestStep?.screenshot_base64 && (
        <View style={styles.pageView}>
          <Image
            source={{ uri: `data:image/png;base64,${latestStep.screenshot_base64}` }}
            style={styles.screenshot}
            resizeMode="contain"
          />
          {latestStep.highlight_box && (
            <View
              pointerEvents="none"
              style={[
                styles.highlight,
                {
                  left: `${latestStep.highlight_box.x}%`,
                  top: `${latestStep.highlight_box.y}%`,
                  width: `${latestStep.highlight_box.width}%`,
                  height: `${latestStep.highlight_box.height}%`,
                },
              ]}
            />
          )}
          <Text style={styles.pageCaption}>Reading the page…</Text>
        </View>
      )}

      {isBrowsing && !latestStep?.screenshot_base64 && (
        <View style={styles.loadingBlock}>
          <ActivityIndicator color={colors.primary} size="large" />
          <Text style={styles.loadingText}>Agent is opening the store…</Text>
        </View>
      )}

      <ScrollView style={styles.timelineScroll} contentContainerStyle={{ padding: spacing.lg }}>
        <Text style={styles.sectionLabel}>Agent activity</Text>
        <Timeline steps={steps} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { ...type.h3, color: colors.textPrimary },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  statusDot: { width: 8, height: 8, borderRadius: radii.pill },
  statusText: { ...type.caption, color: colors.textSecondary },
  pageView: { backgroundColor: '#111', padding: spacing.sm },
  screenshot: { width: '100%', height: 220, borderRadius: radii.md, backgroundColor: '#000' },
  highlight: {
    position: 'absolute',
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: radii.sm,
    backgroundColor: 'rgba(255,77,121,0.15)',
  },
  pageCaption: { ...type.caption, color: colors.white, textAlign: 'center', marginTop: spacing.xs },
  loadingBlock: { alignItems: 'center', paddingVertical: spacing.xl, gap: spacing.sm },
  loadingText: { ...type.body, color: colors.textSecondary },
  timelineScroll: { flex: 1 },
  sectionLabel: { ...type.caption, color: colors.textSecondary, marginBottom: spacing.sm, textTransform: 'uppercase' },
});
