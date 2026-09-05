import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, radii, type } from '../theme';
import { AgentStepEvent, RunStepRecord } from '../api/types';

export default function Timeline({ steps }: { steps: (AgentStepEvent | RunStepRecord)[] }) {
  const total = steps.reduce((sum, s) => sum + s.duration_s, 0);
  return (
    <View>
      {steps.map((s, i) => (
        <View key={`${s.step_number}-${i}`} style={styles.row}>
          <View style={styles.rail}>
            <View style={styles.dot} />
            {i < steps.length - 1 && <View style={styles.line} />}
          </View>
          <View style={styles.content}>
            <View style={styles.titleRow}>
              <Text style={styles.title}>{s.title}</Text>
              <Text style={styles.duration}>{s.duration_s.toFixed(1)}s</Text>
            </View>
            <Text style={styles.description}>{s.description}</Text>
          </View>
        </View>
      ))}
      {steps.length > 0 && (
        <Text style={styles.footer}>Completed in {Math.floor(total / 60)}m {Math.round(total % 60)}s</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row' },
  rail: { width: 24, alignItems: 'center' },
  dot: { width: 10, height: 10, borderRadius: radii.pill, backgroundColor: colors.allow, marginTop: 4 },
  line: { flex: 1, width: 2, backgroundColor: colors.border, marginVertical: 2 },
  content: { flex: 1, paddingBottom: spacing.md },
  titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { ...type.bodyMedium, color: colors.textPrimary, fontFamily: 'Inter_600SemiBold' },
  duration: { ...type.caption, color: colors.textSecondary },
  description: { ...type.caption, color: colors.textSecondary, marginTop: 2 },
  footer: { ...type.caption, color: colors.textSecondary, textAlign: 'center', marginTop: spacing.sm },
});
