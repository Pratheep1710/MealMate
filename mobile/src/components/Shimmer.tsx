import { useEffect, useState } from 'react';
import { Animated, Easing } from 'react-native';

import { isTestEnv } from '../lib/isTestEnv';
import { colors } from '../theme/tokens';

// Matches the design's `spineShimmer` keyframe (opacity .28 <-> .62, 1.8s ease-in-out loop) — used
// for both the per-slot "regenerating" placeholder and the whole-day "still cooking" skeleton, so
// a slot mid-edit and a day that hasn't been generated yet read as the same kind of "in progress."
export function Shimmer({
  width,
  height,
  delay = 0,
  color = colors.shimmerBase,
}: {
  width: number | `${number}%`;
  height: number;
  delay?: number;
  color?: string;
}) {
  // A lazy useState initializer (not useRef().current) keeps this Animated.Value's identity
  // stable across renders without touching a ref during render, per react-hooks/refs.
  const [opacity] = useState(() => new Animated.Value(0.28));

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 0.62,
          duration: 900,
          delay,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.28,
          duration: 900,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    if (!isTestEnv) {
      loop.start();
    }
    return () => loop.stop();
  }, [opacity, delay]);

  return (
    <Animated.View
      style={{
        width,
        height,
        borderRadius: 3,
        backgroundColor: color,
        opacity,
      }}
    />
  );
}
