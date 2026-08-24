import { useEffect, useState } from 'react';
import { Animated, Easing, View } from 'react-native';

import { isTestEnv } from '../lib/isTestEnv';
import { colors } from '../theme/tokens';

// The design's `nowPulse` keyframe: an expanding, fading turmeric ring. Turmeric is reserved
// exclusively for "this is happening right now" per the token system — this is the one place it's
// used as motion rather than a flat fill, marking the current slot's node in the day spine.
export function PulseRing({ size = 13 }: { size?: number }) {
  // Lazy useState initializers (not useRef().current) keep these Animated.Values' identity
  // stable across renders without touching a ref during render, per react-hooks/refs.
  const [scale] = useState(() => new Animated.Value(1));
  const [opacity] = useState(() => new Animated.Value(0.42));

  useEffect(() => {
    const loop = Animated.loop(
      Animated.parallel([
        Animated.timing(scale, {
          toValue: 1.7,
          duration: 2600,
          easing: Easing.out(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0,
          duration: 2600,
          easing: Easing.out(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    if (!isTestEnv) {
      loop.start();
    }
    return () => {
      loop.stop();
      scale.setValue(1);
      opacity.setValue(0.42);
    };
  }, [scale, opacity]);

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Animated.View
        style={{
          position: 'absolute',
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: 2,
          borderColor: colors.turmeric,
          transform: [{ scale }],
          opacity,
        }}
      />
      <View
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: 2,
          borderColor: colors.turmeric,
          backgroundColor: colors.surface,
        }}
      />
    </View>
  );
}
