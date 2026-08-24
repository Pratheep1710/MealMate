import { Circle, Path, Svg } from 'react-native-svg';

// Line-art icon set matching the Claude Design pass (project b56ee743) — stroke-based, round caps,
// no fill, sized to sit inside a 44px+ tap target rather than drawn at tap-target size themselves.
type IconProps = { size?: number; color?: string; strokeWidth?: number };

export function RefreshIcon({ size = 15, color = 'currentColor', strokeWidth = 1.6 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M20 12a8 8 0 11-2.5-5.8M20 4v4h-4"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function ChevronLeftIcon({
  size = 17,
  color = 'currentColor',
  strokeWidth = 1.6,
}: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M15 5l-7 7 7 7"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function ChevronRightSmallIcon({
  size = 8,
  color = 'currentColor',
  strokeWidth = 2,
}: IconProps) {
  return (
    <Svg width={size} height={size * 1.75} viewBox="0 0 8 14" fill="none">
      <Path
        d="M1 1l6 6-6 6"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function ClockIcon({ size = 15, color = 'currentColor', strokeWidth = 1.6 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={12} r={9} stroke={color} strokeWidth={strokeWidth} />
      <Path d="M12 7.5V12l3 2" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  );
}

export function WeekTabIcon({ size = 20, color = 'currentColor', strokeWidth = 1.6 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M4 6h16M4 12h16M4 18h10"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
    </Svg>
  );
}

export function ListTabIcon({ size = 20, color = 'currentColor', strokeWidth = 1.6 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M5 6h14l-1.2 13H6.2L5 6zM9 6V4h6v2"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function PersonTabIcon({ size = 20, color = 'currentColor', strokeWidth = 1.6 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={8} r={3.4} stroke={color} strokeWidth={strokeWidth} />
      <Path
        d="M5 20c1.4-3.4 4-5 7-5s5.6 1.6 7 5"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
    </Svg>
  );
}
