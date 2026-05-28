import { useMemo } from 'react';
import { useLocation, useNavigate, useSearchParams as useRouterSearchParams } from 'react-router-dom';

interface NavigateOptions {
  scroll?: boolean;
}

export function useRouter() {
  const navigate = useNavigate();

  return useMemo(
    () => ({
      push: (href: string, _options?: NavigateOptions) => navigate(href),
      replace: (href: string, _options?: NavigateOptions) => navigate(href, { replace: true }),
      back: () => navigate(-1),
      forward: () => navigate(1),
      refresh: () => window.location.reload(),
      prefetch: async () => undefined,
    }),
    [navigate],
  );
}

export function usePathname() {
  return useLocation().pathname;
}

export function useSearchParams() {
  const [searchParams] = useRouterSearchParams();
  return searchParams;
}