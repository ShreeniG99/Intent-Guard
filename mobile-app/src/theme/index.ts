/**
 * Design tokens for Checkout Integrity Firewall.
 * Palette: pink/coral + gradients, white, light grey (per reference mockups).
 * Typography: Poppins (geometric, Futura-like) for display/headings,
 * Inter (humanist, Proxima-Nova-like) for body -- free, license-safe
 * Google Fonts substitutes for the requested Futura/Proxima Nova blend,
 * since those are commercial fonts that can't be bundled without a license.
 */

export const colors = {
  // Brand pink -- sampled directly from logo.png (#FD4D77) so the app's
  // accent color always matches the logo exactly, not an approximation.
  primary: '#FD4D77',
  primaryDark: '#E13A63',
  primaryLight: '#FE85A3',
  gradientStart: '#FE7A9A',
  gradientEnd: '#FD4D77',

  // Neutrals
  white: '#FFFFFF',
  background: '#F7F7FA',
  surface: '#FFFFFF',
  border: '#ECECF1',
  greyLight: '#F0F0F4',
  grey: '#C9C9D2',

  // Text
  textPrimary: '#1A1A22',
  textSecondary: '#6B6B76',
  textOnPrimary: '#FFFFFF',

  // Verdicts -- each outcome gets its own distinct identity
  allow: '#22C55E',
  allowBg: '#EAFBF1',
  block: '#EF4444',
  blockBg: '#FDECEC',
  revalidate: '#F59E0B',
  revalidateBg: '#FFF7E6',
  refund: '#8B5CF6',
  refundBg: '#F3EEFF',
} as const;

export const gradients = {
  primary: [colors.gradientStart, colors.gradientEnd] as const,
  subtle: [colors.primaryLight, colors.primary] as const,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radii = {
  sm: 8,
  md: 14,
  lg: 20,
  xl: 28,
  pill: 999,
} as const;

export const fonts = {
  display: 'Poppins_700Bold',
  displaySemi: 'Poppins_600SemiBold',
  displayMedium: 'Poppins_500Medium',
  body: 'Inter_400Regular',
  bodyMedium: 'Inter_500Medium',
  bodySemi: 'Inter_600SemiBold',
  bodyBold: 'Inter_700Bold',
} as const;

export const type = {
  h1: { fontFamily: fonts.display, fontSize: 28, lineHeight: 34 },
  h2: { fontFamily: fonts.displaySemi, fontSize: 22, lineHeight: 28 },
  h3: { fontFamily: fonts.displaySemi, fontSize: 18, lineHeight: 24 },
  body: { fontFamily: fonts.body, fontSize: 15, lineHeight: 22 },
  bodyMedium: { fontFamily: fonts.bodyMedium, fontSize: 15, lineHeight: 22 },
  caption: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  button: { fontFamily: fonts.bodySemi, fontSize: 16, lineHeight: 20 },
} as const;

export const shadow = {
  card: {
    shadowColor: '#1A1A22',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 12,
    elevation: 3,
  },
} as const;
