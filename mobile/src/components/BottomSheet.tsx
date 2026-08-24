import { useEffect, useState } from 'react';
import { Animated, Easing, Modal, Pressable, StyleSheet, View, type ViewStyle } from 'react-native';

import { colors, radii, spacing } from '../theme/tokens';

// Matches the design's sheet treatment: dim scrim, 20px top-corner radius, a slide-up entrance
// (its `sheetUp` keyframe — 18px translateY + fade, ~220ms ease-out).
export function BottomSheet({
  visible,
  onClose,
  children,
  contentStyle,
}: {
  visible: boolean;
  onClose: () => void;
  children: React.ReactNode;
  contentStyle?: ViewStyle;
}) {
  // Lazy useState initializers (not useRef().current) keep these Animated.Values' identity
  // stable across renders without touching a ref during render, per react-hooks/refs.
  const [translateY] = useState(() => new Animated.Value(18));
  const [opacity] = useState(() => new Animated.Value(0));

  useEffect(() => {
    if (visible) {
      translateY.setValue(18);
      opacity.setValue(0);
      Animated.parallel([
        Animated.timing(translateY, {
          toValue: 0,
          duration: 220,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 1,
          duration: 220,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [visible, translateY, opacity]);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={styles.scrim}
        onPress={onClose}
        testID="bottom-sheet-scrim"
        accessibilityLabel="Close"
      />
      <Animated.View style={[styles.sheet, contentStyle, { transform: [{ translateY }], opacity }]}>
        <View style={styles.handle} />
        {children}
      </Animated.View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.overlayScrim,
  },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surfaceSheet,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
  },
  handle: {
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.handleBar,
    alignSelf: 'center',
    marginBottom: spacing.lg,
  },
});
