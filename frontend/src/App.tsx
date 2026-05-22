import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout";
import { AuthGate } from "@/components/auth-gate";
import { LandingPage } from "@/pages/landing";
import { LoginPage } from "@/pages/login";
import { ForgotPasswordPage } from "@/pages/forgot-password";
import { ResetPasswordPage } from "@/pages/reset-password";
import { VerifyEmailPage } from "@/pages/verify-email";
import { GoogleCallbackPage } from "@/pages/google-callback";
import { OverviewPage } from "@/pages/overview";
import { UploadPage } from "@/pages/upload";
import { PlatformsPage } from "@/pages/platforms";
import { LibraryPage } from "@/pages/library";
import { SettingsPage } from "@/pages/settings";
import { PrivacyPage } from "@/pages/legal/privacy";
import { TermsPage } from "@/pages/legal/terms";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/auth/google" element={<GoogleCallbackPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route element={<AuthGate />}>
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<OverviewPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/platforms" element={<PlatformsPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
