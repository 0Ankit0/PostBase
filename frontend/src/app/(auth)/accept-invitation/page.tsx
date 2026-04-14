'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import {
  useAcceptInvitation,
  useDeclineInvitation,
  useMyTenantInvitations,
} from '@/hooks/use-tenants';
import { useAuthStore } from '@/store/auth-store';
import { Button } from '@/components/ui/button';

function AcceptInvitationPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get('token');
  const { isAuthenticated } = useAuthStore();
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [activeDecision, setActiveDecision] = useState<'accept' | 'decline' | null>(null);

  const acceptInvitation = useAcceptInvitation();
  const declineInvitation = useDeclineInvitation();
  const { data: invitationData } = useMyTenantInvitations({ status: 'pending', limit: 100 });

  const invitation = useMemo(
    () => invitationData?.items.find((item) => item.token === token),
    [invitationData?.items, token]
  );

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage('No invitation token found in the URL.');
      return;
    }

    if (!isAuthenticated) {
      router.push(`/login?redirect=${encodeURIComponent(`/accept-invitation?token=${token}`)}`);
    }
  }, [isAuthenticated, router, token]);

  const handleDecision = async (decision: 'accept' | 'decline') => {
    if (!token) {
      return;
    }

    setActiveDecision(decision);
    setStatus('loading');
    try {
      if (decision === 'accept') {
        await acceptInvitation.mutateAsync(token);
        setMessage('You have successfully joined the organization.');
      } else {
        await declineInvitation.mutateAsync(token);
        setMessage('Invitation declined.');
      }
      setStatus('success');
      setTimeout(() => router.push('/tenants'), 1500);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setStatus('error');
      setMessage(axiosErr?.response?.data?.detail || 'Failed to process the invitation.');
    } finally {
      setActiveDecision(null);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md rounded-xl bg-white p-8 shadow text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Team Invitation</h1>

        {status === 'idle' && token && isAuthenticated && (
          <div className="space-y-4">
            <p className="text-gray-600">
              {invitation
                ? `You were invited to join ${invitation.tenant_name} (${invitation.tenant_slug}) as ${invitation.role}.`
                : 'Choose whether you want to accept or decline this invitation.'}
            </p>
            <div className="flex justify-center gap-3">
              <Button
                onClick={() => handleDecision('accept')}
                isLoading={activeDecision === 'accept'}
                disabled={activeDecision !== null}
              >
                Accept invitation
              </Button>
              <Button
                variant="outline"
                onClick={() => handleDecision('decline')}
                isLoading={activeDecision === 'decline'}
                disabled={activeDecision !== null}
              >
                Decline invitation
              </Button>
            </div>
          </div>
        )}

        {status === 'loading' && <p className="text-gray-500">Processing your invitation...</p>}

        {status === 'success' && (
          <>
            <div className="mb-4 text-green-600 text-4xl">✓</div>
            <p className="text-gray-700">{message}</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="mb-4 text-red-500 text-4xl">✗</div>
            <p className="text-gray-700">{message}</p>
          </>
        )}
      </div>
    </div>
  );
}

export default function AcceptInvitationPage() {
  return (
    <Suspense>
      <AcceptInvitationPageInner />
    </Suspense>
  );
}
