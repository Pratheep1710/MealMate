import { Circle, Path, Svg } from 'react-native-svg';

// Line-art icon set matching the Claude Design pass (project b56ee743) — stroke-based, round caps,
// no fill, sized to sit inside a 44px+ tap target rather than drawn at tap-target size themselves.
type IconProps = { size?: number; color?: string; strokeWidth?: number };

// Standard multi-color "G" mark for a "Continue with Google" button — a normal OAuth entry-point
// icon, not a mockup of Google's own account-picker UI (that system sheet is real OS/Google
// chrome and isn't something this app draws).
export function GoogleIcon({ size = 18 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 48 48">
      <Path
        fill="#4285F4"
        d="M45 24c0-1.6-.1-2.7-.4-4H24v8h12c-.2 2-1.5 5-4.7 7l6.4 5C41.4 36.5 45 31 45 24z"
      />
      <Path
        fill="#34A853"
        d="M24 46c5.9 0 10.9-2 14.5-5.3l-6.4-5c-1.9 1.3-4.5 2.2-8.1 2.2-6 0-11.1-3.9-12.9-9.3l-6.7 5.2C8 40.8 15.4 46 24 46z"
      />
      <Path
        fill="#FBBC05"
        d="M11.1 28.6A13.6 13.6 0 0 1 10.4 24c0-1.6.3-3.2.7-4.6l-6.7-5.2A22 22 0 0 0 2 24c0 3.5.9 6.9 2.4 9.8l6.7-5.2z"
      />
      <Path
        fill="#EA4335"
        d="M24 10.3c4.2 0 7.1 1.8 8.8 3.4l6-5.9C35 4.3 30 2 24 2 15.4 2 8 7.2 4.4 14.2l6.7 5.2C12.9 14.1 18 10.3 24 10.3z"
      />
    </Svg>
  );
}

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

export function LeafIcon({ size = 15, color = 'currentColor', strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 20c5-1 8-5 8-11-6 0-9 3-9 8"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      <Path d="M11 20V9" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
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
