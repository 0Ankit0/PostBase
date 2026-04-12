'use client';

import { ShieldCheck } from 'lucide-react';

import type { AuthAuditTimelineEvent } from '@/types';

export function AuthAuditTimeline({ events }: { events: AuthAuditTimelineEvent[] }) {
  return (
    <div className="rounded-3xl border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-blue-600" />
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Auth timeline</p>
      </div>
      <div className="space-y-3">
        {events.map((event) => (
          <div key={event.id} className="rounded-xl border border-gray-200 px-3 py-2">
            <p className="text-sm font-medium text-gray-900">{event.event_name}</p>
            <p className="text-xs text-gray-500">{new Date(event.created_at).toLocaleString()} · {event.subject}#{event.subject_id}</p>
          </div>
        ))}
        {!events.length ? <p className="text-xs text-gray-500">No auth timeline events match this filter.</p> : null}
      </div>
    </div>
  );
}
