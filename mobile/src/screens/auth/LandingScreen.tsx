import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { BottomSheet } from '../../components/BottomSheet';
import { GoogleIcon, LeafIcon } from '../../components/icons';
import type { AuthStackParamList } from '../../navigation/types';
import { colors, fonts, radii, spacing } from '../../theme/tokens';
import { SampleDaySpine } from './SampleDaySpine';

// MP-027/028 design pass, Auth (project b56ee743, "Meal Planner Auth.dc.html"): the pre-auth
// landing screen — a real day on the spine (illustrative, see SampleDaySpine), then two ways in.
// "Continue with Google" is a real button that opens a calm "not set up yet" sheet rather than a
// working OAuth flow (no Google OAuth client is registered with Supabase yet). "Continue with
// email" isn't in the original design — it's the one addition needed so the app has a real,
// working way in today, since phone/OTP and Google both need infrastructure only the project
// owner can provision. See docs/MP-027-design-pass-scope.md.
export function LandingScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<AuthStackParamList, 'Landing'>>();
  const [googleSheetOpen, setGoogleSheetOpen] = useState(false);

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.brandRow}>
          <View style={styles.brandMark}>
            <LeafIcon size={15} color={colors.ground} />
          </View>
          <Text style={styles.brandName}>Ennanga Samayal</Text>
        </View>

        <View style={styles.heroBlock}>
          <Text style={styles.heroTitle}>Someone already thought about dinner.</Text>
          <Text style={styles.heroBody}>
            A week of meals in your own kitchen&apos;s rhythm. Change anything you like — it&apos;s
            a suggestion, not a schedule.
          </Text>
        </View>

        <SampleDaySpine />

        <View style={styles.spacer} />

        <View style={styles.actions}>
          <TouchableOpacity
            style={styles.googleButton}
            onPress={() => setGoogleSheetOpen(true)}
            testID="landing-google"
          >
            <GoogleIcon size={19} />
            <Text style={styles.googleLabel}>Continue with Google</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.phoneButton}
            onPress={() => navigation.navigate('PhonePreview')}
            testID="landing-phone"
          >
            <Text style={styles.phoneLabel}>Continue with mobile number</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.emailLink}
            onPress={() => navigation.navigate('SignUp')}
            testID="landing-email"
          >
            <Text style={styles.emailLinkLabel}>Continue with email</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.signInRow}
            onPress={() => navigation.navigate('SignIn')}
            testID="landing-sign-in"
          >
            <Text style={styles.signInPrompt}>Already set up? </Text>
            <Text style={styles.signInLink}>Sign in</Text>
          </TouchableOpacity>

          <Text style={styles.footerNote}>No card. No calorie counting. No streaks.</Text>
        </View>
      </ScrollView>

      <BottomSheet visible={googleSheetOpen} onClose={() => setGoogleSheetOpen(false)}>
        <Text style={styles.sheetKicker}>Continue with Google</Text>
        <Text style={styles.sheetTitle}>Not quite ready</Text>
        <Text style={styles.sheetNote}>
          Google sign-in isn&apos;t set up yet. Use email or a mobile number for now.
        </Text>
        <TouchableOpacity style={styles.sheetButton} onPress={() => setGoogleSheetOpen(false)}>
          <Text style={styles.sheetButtonLabel}>Got it</Text>
        </TouchableOpacity>
      </BottomSheet>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.ground,
  },
  scroll: {
    padding: spacing.xl,
    paddingTop: 48,
    paddingBottom: 40,
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  brandMark: {
    width: 26,
    height: 26,
    borderRadius: 7,
    backgroundColor: colors.leaf,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandName: {
    fontFamily: fonts.bodyRegular,
    fontSize: 12,
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    color: colors.textSecondary,
  },
  heroBlock: {
    gap: spacing.md,
    paddingTop: 30,
    paddingBottom: spacing.xl,
  },
  heroTitle: {
    fontFamily: fonts.displayLight,
    fontSize: 36,
    lineHeight: 40,
    color: colors.textPrimary,
  },
  heroBody: {
    fontFamily: fonts.bodyRegular,
    fontSize: 15,
    lineHeight: 22,
    color: colors.textSecondary,
  },
  spacer: {
    height: spacing.xl,
  },
  actions: {
    gap: spacing.sm,
  },
  googleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 11,
    minHeight: 56,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radii.lg,
    backgroundColor: colors.surface,
  },
  googleLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 16,
    color: colors.textPrimary,
  },
  phoneButton: {
    minHeight: 56,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.leaf,
    borderRadius: radii.lg,
  },
  phoneLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 16,
    color: colors.leaf,
  },
  emailLink: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emailLinkLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
    textDecorationLine: 'underline',
  },
  signInRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
  },
  signInPrompt: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
  },
  signInLink: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.leaf,
    textDecorationLine: 'underline',
  },
  footerNote: {
    fontFamily: fonts.bodyRegular,
    fontSize: 12,
    lineHeight: 18,
    color: colors.textFaint,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  sheetKicker: {
    fontFamily: fonts.bodyRegular,
    fontSize: 10,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    color: colors.textMuted,
    marginBottom: 2,
  },
  sheetTitle: {
    fontFamily: fonts.displayLight,
    fontSize: 26,
    lineHeight: 31,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  sheetNote: {
    fontFamily: fonts.bodyRegular,
    fontSize: 13,
    lineHeight: 19,
    color: colors.textMuted,
    marginBottom: spacing.lg,
  },
  sheetButton: {
    minHeight: 48,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sheetButtonLabel: {
    fontFamily: fonts.bodyRegular,
    fontSize: 14,
    color: colors.textSecondary,
  },
});
