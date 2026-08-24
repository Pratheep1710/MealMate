// Design tokens from the Claude Design pass (claude.ai/design project b56ee743, "Meal Planner.dc.html").
// Grounded in a Tamil Nadu home kitchen rather than a generic "healthy eating app" look: the named
// colors below are the ones the design system itself uses (iron kadai, banana leaf, turmeric,
// eversilver, washed steel) — kept as the literal token names so this file stays the single place
// that vocabulary is spelled out.

export const colors = {
  // Core palette
  ink: '#1A2420', // iron kadai — primary text
  leaf: '#1E5B3C', // banana leaf — primary action/accent
  turmeric: '#C4881A', // now, only now — reserved exclusively for "this moment" signaling
  steel: '#B9C3BF', // eversilver — muted/past state
  ground: '#F4F6F4', // washed steel — app background

  // Text
  textPrimary: '#1A2420',
  textSecondary: '#4C5A54',
  textMuted: '#6C7A74',
  textFaint: '#7A8781',

  // Surfaces & borders
  surface: '#FFFFFF',
  surfaceSheet: '#F7F9F7',
  border: '#DCE2DF',
  borderStrong: '#C3CCC8',
  hairline: '#E2E7E4',
  divider: '#D3DAD7',

  // Interactive tints
  hoverTint: '#F1F4F1',
  accentTintHover: '#EAF2EC',
  accentTintActive: '#F2F7F3',
  neutralTintHover: '#EBEFEC',
  shimmerBase: '#E7ECE9',
  shimmerBaseSoft: '#EDF0EE',
  shimmerBar: '#DEE4E1',
  handleBar: '#C9D1CD',
  dotOutline: '#CBD4CF',

  overlayScrim: 'rgba(26,36,32,0.34)',

  // Evening-notification dark surface
  nightGradientTop: '#101614',
  nightGradientMid: '#1D2A24',
  nightGradientBottom: '#0E1412',
} as const;

export const radii = {
  sm: 8,
  md: 12,
  lg: 14,
  xl: 20,
  pill: 999,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 22,
  xxl: 28,
} as const;

// Newsreader (display serif, weight 300 default) — dish names and headlines only, never chrome.
// Hanken Grotesk (body/UI sans) — everything else. Tabular figures on all times.
export const fonts = {
  displayLight: 'Newsreader_300Light',
  displayLightItalic: 'Newsreader_300Light_Italic',
  displayRegular: 'Newsreader_400Regular',
  displayMedium: 'Newsreader_500Medium',
  bodyLight: 'HankenGrotesk_300Light',
  bodyRegular: 'HankenGrotesk_400Regular',
  bodyMedium: 'HankenGrotesk_500Medium',
  bodySemiBold: 'HankenGrotesk_600SemiBold',
} as const;

export const minTapTarget = 48;
