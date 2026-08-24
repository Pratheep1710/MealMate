import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { LeafIcon, PersonTabIcon } from '../../components/icons';
import { PulseRing } from '../../components/PulseRing';
import type { AuthStackParamList } from '../../navigation/types';
import { colors, fonts, radii, spacing } from '../../theme/tokens';

// MP-027/028 design pass, Auth: the phone/OTP signup flow exactly as designed — a real, working
// numeric keypad and step-through interaction — but not connected to a real SMS provider (none is
// configured in Supabase yet). Marked "Preview" throughout so it reads as a look-ahead, not a
// working account creation path; "Show me this week" exits back to the real sign-in/sign-up
// screens rather than pretending a session started. See docs/MP-027-design-pass-scope.md.
type Step = 'phone' | 'otp' | 'done';

const OTP_LENGTH = 6;
const PHONE_LENGTH = 10;

function groupPhone(digits: string): string {
  return digits.length > 5 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : digits;
}

export function PhonePreviewScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<AuthStackParamList, 'PhonePreview'>>();
  const [step, setStep] = useState<Step>('phone');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (advanceTimer.current) {
        clearTimeout(advanceTimer.current);
      }
    };
  }, []);

  const press = (digit: string) => {
    if (step === 'phone') {
      setPhone((p) => (p + digit).slice(0, PHONE_LENGTH));
      return;
    }
    if (step === 'otp') {
      setOtp((o) => {
        const next = (o + digit).slice(0, OTP_LENGTH);
        if (next.length === OTP_LENGTH) {
          advanceTimer.current = setTimeout(() => setStep('done'), 420);
        }
        return next;
      });
    }
  };

  const del = () => {
    if (step === 'phone') {
      setPhone((p) => p.slice(0, -1));
    } else if (step === 'otp') {
      setOtp((o) => o.slice(0, -1));
    }
  };

  const goBack = () => {
    if (step === 'otp') {
      setOtp('');
      setStep('phone');
    } else {
      navigation.goBack();
    }
  };

  const primaryReady = step === 'phone' ? phone.length === PHONE_LENGTH : otp.length === OTP_LENGTH;
  const primaryLabel = step === 'phone' ? 'Send the code' : 'Verify';
  const onPrimary = () => {
    if (!primaryReady) return;
    if (step === 'phone') {
      setStep('otp');
    } else if (step === 'otp') {
      setStep('done');
    }
  };

  return (
    <View style={styles.container}>
      {step !== 'done' && (
        <View style={styles.header}>
          <TouchableOpacity
            onPress={goBack}
            style={styles.backButton}
            testID="phone-preview-back"
            accessibilityLabel="Back"
          >
            <Text style={styles.backGlyph}>‹</Text>
          </TouchableOpacity>
          <View style={styles.pipRow}>
            <View style={[styles.pip, styles.pipOn]} />
            <View style={[styles.pip, step !== 'phone' && styles.pipOn]} />
            <View style={styles.pip} />
          </View>
          <Text style={styles.previewBadge}>Preview</Text>
        </View>
      )}

      <View style={styles.content}>
        {step === 'phone' && (
          <PhoneStep
            phone={phone}
            onChangeVisual={groupPhone(phone)}
            ready={phone.length === PHONE_LENGTH}
          />
        )}
        {step === 'otp' && <OtpStep otp={otp} phone={phone} />}
        {step === 'done' && <DoneStep onShowWeek={() => navigation.navigate('SignIn')} />}
      </View>

      {step !== 'done' && (
        <Keypad
          onPress={press}
          onDelete={del}
          onPrimary={onPrimary}
          primaryLabel={primaryLabel}
          primaryReady={primaryReady}
        />
      )}
    </View>
  );
}

function PhoneStep({
  phone,
  onChangeVisual,
  ready,
}: {
  phone: string;
  onChangeVisual: string;
  ready: boolean;
}) {
  return (
    <>
      <Text style={styles.stepTitle}>Your mobile number</Text>
      <Text style={styles.stepBody}>
        We send a six-digit code. No password to invent, no email to confirm.
      </Text>
      <View style={styles.phoneInputRow}>
        <Text style={styles.countryCode}>+91</Text>
        <Text style={styles.phoneDigits} testID="phone-preview-digits">
          {onChangeVisual}
        </Text>
        <View style={styles.caret} />
      </View>
      <Text style={styles.hint}>
        {ready ? 'Looks right. Send the code.' : 'Ten digits. Indian numbers only, for now.'}
      </Text>
    </>
  );
}

function OtpStep({ otp, phone }: { otp: string; phone: string }) {
  const boxes = Array.from({ length: OTP_LENGTH }, (_, i) => otp[i] ?? '');
  return (
    <>
      <Text style={styles.stepTitle}>Enter the code</Text>
      <Text style={styles.stepBody}>Sent to +91 {groupPhone(phone)}.</Text>
      <View style={styles.otpRow}>
        {boxes.map((char, i) => (
          <View
            key={i}
            style={[
              styles.otpBox,
              char ? styles.otpBoxFilled : null,
              i === otp.length ? styles.otpBoxActive : null,
            ]}
          >
            <Text style={styles.otpChar}>{char}</Text>
          </View>
        ))}
      </View>
      <Text style={styles.hint}>
        {otp.length === OTP_LENGTH
          ? 'Checking…'
          : 'Resend in 0:24. It usually lands before you look up.'}
      </Text>
    </>
  );
}

function DoneStep({ onShowWeek }: { onShowWeek: () => void }) {
  return (
    <View style={styles.doneContainer}>
      <View style={styles.doneHeader}>
        <PulseRing size={26} />
        <Text style={styles.doneTitle}>You&apos;re in.</Text>
        <Text style={styles.doneBody}>
          This is a preview of what phone sign-in will feel like — nothing was actually created.
          Continue with email or sign in to use the real thing today.
        </Text>
      </View>

      <View style={styles.doneCard}>
        <Text style={styles.doneCardKicker}>Two quick things, whenever you like</Text>
        <View style={styles.doneCardRow}>
          <PersonTabIcon size={16} color={colors.leaf} />
          <Text style={styles.doneCardLabel}>Who&apos;s eating, and how many</Text>
        </View>
        <View style={styles.doneCardDivider} />
        <View style={styles.doneCardRow}>
          <LeafIcon size={16} color={colors.leaf} />
          <Text style={styles.doneCardLabel}>Anything you&apos;d rather not see</Text>
        </View>
      </View>

      <View style={{ flex: 1 }} />

      <TouchableOpacity
        style={styles.doneButton}
        onPress={onShowWeek}
        testID="phone-preview-done-cta"
      >
        <Text style={styles.doneButtonLabel}>Continue with email or sign in</Text>
      </TouchableOpacity>
    </View>
  );
}

function Keypad({
  onPress,
  onDelete,
  onPrimary,
  primaryLabel,
  primaryReady,
}: {
  onPress: (digit: string) => void;
  onDelete: () => void;
  onPrimary: () => void;
  primaryLabel: string;
  primaryReady: boolean;
}) {
  const rows = [
    ['1', '2', '3'],
    ['4', '5', '6'],
    ['7', '8', '9'],
    ['', '0', 'del'],
  ];
  return (
    <View style={styles.keypad}>
      {rows.map((row, rowIndex) => (
        <View key={rowIndex} style={styles.keyRow}>
          {row.map((key, colIndex) => {
            if (key === '') {
              return <View key={colIndex} style={styles.key} />;
            }
            if (key === 'del') {
              return (
                <TouchableOpacity
                  key={colIndex}
                  style={[styles.key, styles.keyPlain]}
                  onPress={onDelete}
                  testID="phone-preview-delete"
                >
                  <Text style={styles.keyPlainLabel}>Delete</Text>
                </TouchableOpacity>
              );
            }
            return (
              <TouchableOpacity
                key={colIndex}
                style={styles.key}
                onPress={() => onPress(key)}
                testID={`phone-preview-key-${key}`}
              >
                <Text style={styles.keyLabel}>{key}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      ))}
      <TouchableOpacity
        style={[styles.primaryButton, primaryReady && styles.primaryButtonReady]}
        onPress={onPrimary}
        disabled={!primaryReady}
        testID="phone-preview-primary"
      >
        <Text style={[styles.primaryLabel, primaryReady && styles.primaryLabelReady]}>
          {primaryLabel}
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.ground,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingTop: 56,
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xs,
  },
  backButton: {
    width: 44,
    height: 44,
    marginLeft: -10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backGlyph: {
    fontSize: 28,
    color: colors.textPrimary,
    lineHeight: 28,
  },
  pipRow: {
    flex: 1,
    flexDirection: 'row',
    gap: 5,
  },
  pip: {
    flex: 1,
    height: 3,
    borderRadius: 2,
    backgroundColor: colors.border,
  },
  pipOn: {
    backgroundColor: colors.leaf,
  },
  previewBadge: {
    fontFamily: fonts.bodyRegular,
    fontSize: 10,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: colors.turmeric,
  },
  content: {
    flex: 1,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
  },
  stepTitle: {
    fontFamily: fonts.displayLight,
    fontSize: 30,
    lineHeight: 34,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  stepBody: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    lineHeight: 20,
    color: colors.textSecondary,
    marginBottom: spacing.lg,
  },
  phoneInputRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.md,
    paddingBottom: spacing.md,
    borderBottomWidth: 1.5,
    borderBottomColor: colors.leaf,
  },
  countryCode: {
    fontFamily: fonts.displayLight,
    fontSize: 26,
    color: colors.textSecondary,
  },
  phoneDigits: {
    fontFamily: fonts.displayLight,
    fontSize: 26,
    letterSpacing: 1,
    color: colors.textPrimary,
  },
  caret: {
    width: 2,
    height: 24,
    backgroundColor: colors.turmeric,
  },
  hint: {
    fontFamily: fonts.bodyRegular,
    fontSize: 12,
    color: colors.textFaint,
    marginTop: spacing.md,
  },
  otpRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  otpBox: {
    flex: 1,
    height: 56,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  otpBoxFilled: {
    borderColor: colors.leaf,
  },
  otpBoxActive: {
    borderColor: colors.turmeric,
    borderWidth: 1.5,
  },
  otpChar: {
    fontFamily: fonts.displayLight,
    fontSize: 24,
    color: colors.textPrimary,
  },
  doneContainer: {
    flex: 1,
    gap: spacing.lg,
  },
  doneHeader: {
    gap: spacing.sm,
  },
  doneTitle: {
    fontFamily: fonts.displayLight,
    fontSize: 30,
    color: colors.textPrimary,
  },
  doneBody: {
    fontFamily: fonts.bodyRegular,
    fontSize: 15,
    lineHeight: 21,
    color: colors.textSecondary,
  },
  doneCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  doneCardKicker: {
    fontFamily: fonts.bodyRegular,
    fontSize: 10,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: colors.textMuted,
  },
  doneCardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: 40,
  },
  doneCardDivider: {
    height: 1,
    backgroundColor: colors.hairline,
  },
  doneCardLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 15,
    color: colors.textPrimary,
  },
  doneButton: {
    minHeight: 56,
    borderWidth: 1,
    borderColor: colors.leaf,
    borderRadius: radii.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xl,
  },
  doneButtonLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    color: colors.leaf,
  },
  keypad: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xl,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surfaceSheet,
    gap: spacing.sm,
  },
  keyRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  key: {
    flex: 1,
    height: 52,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  keyPlain: {
    borderWidth: 0,
    backgroundColor: 'transparent',
  },
  keyLabel: {
    fontFamily: fonts.displayLight,
    fontSize: 24,
    color: colors.textPrimary,
  },
  keyPlainLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    color: colors.textSecondary,
  },
  primaryButton: {
    minHeight: 56,
    marginTop: spacing.xs,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonReady: {
    borderColor: colors.leaf,
    backgroundColor: colors.accentTintHover,
  },
  primaryLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 16,
    color: colors.textFaint,
  },
  primaryLabelReady: {
    color: colors.leaf,
  },
});
