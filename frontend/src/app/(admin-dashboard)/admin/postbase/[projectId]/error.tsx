'use client';

import { useEffect } from 'react';
import { Button } from '@/components/ui/button';

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function PostBaseProjectError({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    console.error('PostBase project page error boundary:', error);
  }, [error]);

  return (
    <div className="space-y-4 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      <p className="font-semibold">Control plane panel failed to load.</p>
      <p>{error.message || 'Unexpected error while rendering PostBase controls.'}</p>
      <Button size="sm" variant="outline" onClick={reset}>
        Retry render
      </Button>
    </div>
  );
}
