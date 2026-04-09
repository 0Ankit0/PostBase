'use client';

import Link from 'next/link';
import { Server, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { usePostBaseProjects } from '@/hooks';

export default function PostBaseAdminPage() {
  const projectsQuery = usePostBaseProjects();
  const { data, isLoading, error, refetch, isRefetchError } = projectsQuery;
  const projects = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">PostBase Control Plane</h1>
        <p className="text-sm text-gray-500">
          Projects, environments, provider bindings, secrets, health, and usage visibility.
        </p>
      </div>

      {isLoading && projects.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-sm text-gray-500">Loading PostBase projects...</CardContent>
        </Card>
      ) : error && projects.length === 0 ? (
        <Card>
          <CardContent className="space-y-3 pt-6 text-sm">
            <p className="rounded border border-red-200 bg-red-50 p-2 text-red-700">Failed to load projects. Please retry.</p>
            <button
              className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              onClick={() => void refetch()}
            >
              Retry
            </button>
          </CardContent>
        </Card>
      ) : (
        <>
          {isRefetchError && (
            <div className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              Using cached projects while background refresh retries.
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {projects.map((project) => (
              <Link key={project.id} href={`/admin/postbase/${project.id}`}>
                <Card className="cursor-pointer transition-shadow hover:shadow-md">
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between text-base">
                      <span className="flex items-center gap-2">
                        <Server className="h-4 w-4 text-blue-600" />
                        {project.name}
                      </span>
                      <ChevronRight className="h-4 w-4 text-gray-400" />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1 text-sm text-gray-600">
                    <p>Slug: {project.slug}</p>
                    <p>Status: {project.is_active ? 'active' : 'inactive'}</p>
                    <p className="line-clamp-2">{project.description || 'No description provided.'}</p>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
