import { Pressable, Text, StyleSheet, ViewStyle, ActivityIndicator } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, gradients, radii, spacing, type } from '../theme';

interface Props {
  label: string;
  onPress: () => void;
  style?: ViewStyle;
  disabled?: boolean;
  loading?: boolean;
  /** Defaults to a full pill. Pass 0 for square corners, or any radii.* value. */
  borderRadius?: number;
}

export default function GradientButton({ label, onPress, style, disabled, loading, borderRadius = radii.pill }: Props) {
  return (
    <Pressable onPress={onPress} disabled={disabled || loading} style={({ pressed }) => [{ opacity: pressed ? 0.85 : 1 }, style]}>
      <LinearGradient
        colors={disabled ? [colors.grey, colors.grey] : gradients.primary}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        style={[styles.button, { borderRadius }]}
      >
        {loading ? <ActivityIndicator color={colors.white} /> : <Text style={styles.label}>{label}</Text>}
      </LinearGradient>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    paddingVertical: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { ...type.button, color: colors.white },
});
