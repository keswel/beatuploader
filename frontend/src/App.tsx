import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout";
import { AuthGate } from "@/components/auth-gate";
import { LandingPage } from "@/pages/landing";
import { EarlyAccessPage } from "@/pages/early-access";
import { ScrollOnNavigate } from "@/components/site-chrome";
import { OverviewPage } from "@/pages/overview";
import { UploadPage } from "@/pages/upload";
import { PlatformsPage } from "@/pages/platforms";
import { LibraryPage } from "@/pages/library";
import { SettingsPage } from "@/pages/settings";
import { PrivacyPage } from "@/pages/legal/privacy";
import { TermsPage } from "@/pages/legal/terms";
import { IS_DESKTOP } from "@/lib/target";

// The hosted-account pages (login, forgot/reset password, verify email, Google
// callback) are still in src/pages but intentionally unrouted: the product is
// now the desktop app, and the website only markets + distributes it.

export default function App() {
  return IS_DESKTOP ? <DesktopRoutes /> : <WebsiteRoutes />;
}

function WebsiteRoutes() {
  return (
    <>
      <ScrollOnNavigate />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/early-access" element={<EarlyAccessPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

function DesktopRoutes() {
  return (
    <Routes>
      <Route element={<AuthGate />}>
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<OverviewPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/platforms" element={<PlatformsPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
