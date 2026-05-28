import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Navigate, Outlet, Route, Routes, useParams } from 'react-router-dom';
import HomePage from '@/app/page';
import AuthLayout from '@/app/(auth)/layout';
import LoginPage from '@/app/(auth)/login/page';
import SignupPage from '@/app/(auth)/signup/page';
import ForgotPasswordPage from '@/app/(auth)/forgot-password/page';
import ResetPasswordPage from '@/app/(auth)/reset-password/page';
import OtpVerifyPage from '@/app/(auth)/otp-verify/page';
import VerifyEmailPage from '@/app/(auth)/verify-email/page';
import AuthCallbackPage from '@/app/(auth)/auth-callback/page';
import PaymentCallbackPage from '@/app/(auth)/payment-callback/page';
import AcceptInvitationPage from '@/app/(auth)/accept-invitation/page';
import UserDashboardLayout from '@/app/(user-dashboard)/layout';
import DashboardPage from '@/app/(user-dashboard)/dashboard/page';
import FinancesPage from '@/app/(user-dashboard)/finances/page';
import ProfilePage from '@/app/(user-dashboard)/profile/page';
import SettingsPage from '@/app/(user-dashboard)/settings/page';
import NotificationsPage from '@/app/(user-dashboard)/notifications/page';
import MapsPage from '@/app/(user-dashboard)/maps/page';
import RbacPage from '@/app/(user-dashboard)/rbac/page';
import RoleManagePage from '@/app/(user-dashboard)/rbac/[roleId]/page';
import TokensPage from '@/app/(user-dashboard)/tokens/page';
import TenantsPage from '@/app/(user-dashboard)/tenants/page';
import AdminDashboardLayout from '@/app/(admin-dashboard)/layout';
import AdminDashboardPage from '@/app/(admin-dashboard)/admin/dashboard/page';
import AdminLogsPage from '@/app/(admin-dashboard)/admin/logs/page';
import AdminUsersPage from '@/app/(admin-dashboard)/admin/users/page';
import AdminRbacPage from '@/app/(admin-dashboard)/admin/rbac/page';
import AdminRoleManagePage from '@/app/(admin-dashboard)/admin/rbac/[roleId]/page';
import AdminPostBasePage from '@/app/(admin-dashboard)/admin/postbase/page';
import AdminPostBaseProjectPage from '@/app/(admin-dashboard)/admin/postbase/[projectId]/page';
import AdminPostBaseProjectError from '@/app/(admin-dashboard)/admin/postbase/[projectId]/error';
import AdminSecurityReviewPage from '@/app/(admin-dashboard)/admin/security-review/page';

function AuthRoutes() {
  return (
    <AuthLayout>
      <Outlet />
    </AuthLayout>
  );
}

function UserDashboardRoutes() {
  return (
    <UserDashboardLayout>
      <Outlet />
    </UserDashboardLayout>
  );
}

function AdminDashboardRoutes() {
  return (
    <AdminDashboardLayout>
      <Outlet />
    </AdminDashboardLayout>
  );
}

function UserRoleManageRoute() {
  const { roleId = '' } = useParams();
  return <RoleManagePage params={Promise.resolve({ roleId })} />;
}

function AdminRoleManageRoute() {
  const { roleId = '' } = useParams();
  return <AdminRoleManagePage params={Promise.resolve({ roleId })} />;
}

function AdminPostBaseProjectRoute() {
  const { projectId = '' } = useParams();

  return (
    <RouteErrorBoundary fallback={AdminPostBaseProjectError}>
      <AdminPostBaseProjectPage params={{ projectId }} />
    </RouteErrorBoundary>
  );
}

interface RouteErrorBoundaryProps {
  children: ReactNode;
  fallback: (props: { error: Error; reset: () => void }) => ReactNode;
}

interface RouteErrorBoundaryState {
  error: Error | null;
}

class RouteErrorBoundary extends Component<RouteErrorBoundaryProps, RouteErrorBoundaryState> {
  state: RouteErrorBoundaryState = {
    error: null,
  };

  static getDerivedStateFromError(error: Error): RouteErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Route render failed:', error, errorInfo);
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      const Fallback = this.props.fallback;
      return <>{Fallback({ error: this.state.error, reset: this.reset })}</>;
    }

    return this.props.children;
  }
}

export function AppRouter() {
  return (
    <Routes>
      <Route index element={<HomePage />} />

      <Route element={<AuthRoutes />}>
        <Route path="login" element={<LoginPage />} />
        <Route path="signup" element={<SignupPage />} />
        <Route path="forgot-password" element={<ForgotPasswordPage />} />
        <Route path="reset-password" element={<ResetPasswordPage />} />
        <Route path="otp-verify" element={<OtpVerifyPage />} />
        <Route path="verify-email" element={<VerifyEmailPage />} />
        <Route path="auth-callback" element={<AuthCallbackPage />} />
        <Route path="payment-callback" element={<PaymentCallbackPage />} />
        <Route path="accept-invitation" element={<AcceptInvitationPage />} />
      </Route>

      <Route element={<UserDashboardRoutes />}>
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="finances" element={<FinancesPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="maps" element={<MapsPage />} />
        <Route path="rbac" element={<RbacPage />} />
        <Route path="rbac/:roleId" element={<UserRoleManageRoute />} />
        <Route path="tokens" element={<TokensPage />} />
        <Route path="tenants" element={<TenantsPage />} />
      </Route>

      <Route element={<AdminDashboardRoutes />}>
        <Route path="admin/dashboard" element={<AdminDashboardPage />} />
        <Route path="admin/logs" element={<AdminLogsPage />} />
        <Route path="admin/users" element={<AdminUsersPage />} />
        <Route path="admin/rbac" element={<AdminRbacPage />} />
        <Route path="admin/rbac/:roleId" element={<AdminRoleManageRoute />} />
        <Route path="admin/postbase" element={<AdminPostBasePage />} />
        <Route path="admin/postbase/:projectId" element={<AdminPostBaseProjectRoute />} />
        <Route path="admin/security-review" element={<AdminSecurityReviewPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}