'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { SignupForm } from '@/components/auth/signup-form';
import { apiClient } from '@/lib/api-client';
import { getEnabledProviders, type OAuthProvider } from '@/lib/oauth';

export default function SignupPage() {
  const router = useRouter();
  const [enabledProviders, setEnabledProviders] = useState<OAuthProvider[]>([]);

  useEffect(() => {
    let isMounted = true;

    const accessToken = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

    if (accessToken) {
      void apiClient.get('/users/me')
        .then(() => {
          if (isMounted) {
            router.push('/dashboard');
          }
        })
        .catch(() => {
          // Ignore invalid sessions and leave the signup form visible.
        });
    }

    void getEnabledProviders().then((providers) => {
      if (isMounted) {
        setEnabledProviders(providers);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [router]);

  return <SignupForm enabledProviders={enabledProviders} />;
}
