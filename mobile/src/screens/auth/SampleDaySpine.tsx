import { StyleSheet, Text, View } from 'react-native';

import { colors, fonts, radii, spacing } from '../../theme/tokens';

// The design's pre-auth "value before signup" card: three illustrative slots ("a Wednesday, for
// instance") shown to someone who isn't signed in yet, so there's nothing real to query. This is
// deliberately sample content, not a placeholder for missing data — the copy and dish names are
// the design's own, kept verbatim.
const SAMPLE = [
  { time: '6:40', dish: 'Idli, coconut chutney', state: 'past' as const },
  { time: '12:45', dish: 'Sambar sadam, poriyal', state: 'now' as const },
  { time: '19:45', dish: 'Dosai, tomato thokku', state: 'upcoming' as const },
];

function nodeStyleFor(state: (typeof SAMPLE)[number]['state']) {
  if (state === 'past') return styles.nodePast;
  if (state === 'now') return styles.nodeNow;
  return styles.nodeUpcoming;
}

export function SampleDaySpine() {
  return (
    <View style={styles.card}>
      <Text style={styles.kicker}>A Wednesday, for instance</Text>
      {SAMPLE.map((item, index) => (
        <View key={item.time} style={styles.row}>
          <Text style={styles.time}>{item.time}</Text>
          <View style={styles.railColumn}>
            {index !== SAMPLE.length - 1 && <View style={styles.rail} />}
            <View style={[styles.nodeBase, nodeStyleFor(item.state)]} />
          </View>
          <Text style={styles.dish}>{item.dish}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xs,
  },
  kicker: {
    fontFamily: fonts.bodyRegular,
    fontSize: 10,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    color: colors.textMuted,
    marginBottom: spacing.xs,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    paddingVertical: 9,
  },
  time: {
    width: 40,
    fontFamily: fonts.bodyRegular,
    fontSize: 12,
    color: colors.textMuted,
    textAlign: 'right',
    paddingTop: 3,
  },
  railColumn: {
    width: 13,
    alignItems: 'center',
    alignSelf: 'stretch',
  },
  rail: {
    position: 'absolute',
    top: 9,
    bottom: -9,
    width: 1,
    backgroundColor: colors.hairline,
  },
  nodeBase: {
    marginTop: 5,
    borderRadius: 6,
  },
  nodePast: {
    width: 9,
    height: 9,
    backgroundColor: colors.steel,
  },
  nodeNow: {
    width: 13,
    height: 13,
    marginTop: 3,
    borderWidth: 2,
    borderColor: colors.turmeric,
    backgroundColor: colors.surface,
  },
  nodeUpcoming: {
    width: 10,
    height: 10,
    borderWidth: 1.5,
    borderColor: colors.leaf,
    backgroundColor: colors.surface,
  },
  dish: {
    flex: 1,
    fontFamily: fonts.displayLight,
    fontSize: 19,
    lineHeight: 23,
    color: colors.textPrimary,
    paddingTop: 1,
  },
});
