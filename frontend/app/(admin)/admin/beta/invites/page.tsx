'use client';

import { useState } from 'react';
import Link from 'next/link';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import * as Tooltip from '@radix-ui/react-tooltip';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function BetaInvitesAdminPage() {
  const { isAdmin, isLoading } = useAdminAuth();
  const { logout } = useAuth();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('instructor_beta');
  const [days, setDays] = useState(14);
  const [source, setSource] = useState('admin_ui');
  const [result, setResult] = useState<{ code: string; join_url: string; welcome_url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }
  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-6">
        <div className="text-center text-sm text-gray-600 dark:text-gray-300">You do not have access to this page.</div>
      </div>
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      if (!token) throw new Error('Not authenticated');
      const res = await fetch(`${API_BASE_URL}/api/beta/invites/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ to_email: email, role, expires_in_days: days, source }),
      });
      if (!res.ok) throw new Error((await res.text()) || `Failed to send invite (${res.status})`);
      const data = await res.json();
      setResult({ code: data.code, join_url: data.join_url, welcome_url: data.welcome_url });
    } catch (err: any) {
      setError(err?.message || 'Failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">iNSTAiNSTRU</Link>
              <h1 className="text-xl font-semibold">Beta Invites</h1>
            </div>
            <div className="flex items-center space-x-3">
              <Tooltip.Provider delayDuration={200}>
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <Link href="/admin/beta/settings" className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60">Settings</Link>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content side="bottom" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Beta settings</Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              </Tooltip.Provider>
              <Tooltip.Provider delayDuration={200}>
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <Link href="/admin/beta/metrics" className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60">Metrics</Link>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content side="bottom" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Performance metrics</Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              </Tooltip.Provider>
              <Tooltip.Provider delayDuration={200}>
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <button onClick={logout} className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 cursor-pointer">Log out</button>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content side="bottom" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Sign out of admin</Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              </Tooltip.Provider>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-4 lg:col-span-4">
            <AdminSidebar />
          </aside>
          <section className="col-span-12 md:col-span-8 lg:col-span-8">
            <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
                <h2 className="mb-2 text-lg font-semibold">Send Founding Instructor Invite</h2>
                <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">Generate an invite code and email a direct link to onboarding. Links include both Join and Welcome URLs.</p>
                <form onSubmit={onSubmit} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Email</label>
                    <input value={email} onChange={(e) => setEmail(e.target.value)} required type="email" className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800" placeholder="instructor@example.com" />
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-sm font-medium mb-1">Role</label>
                      <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800">
                        <option value="instructor_beta">instructor_beta</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1">Expires (days)</label>
                      <input value={days} onChange={(e) => setDays(parseInt(e.target.value || '14', 10))} min={1} max={180} type="number" className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800" />
                    </div>
                    <div>
                      <label className="block textsm font-medium mb-1">Source</label>
                      <input value={source} onChange={(e) => setSource(e.target.value)} className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800" />
                    </div>
                  </div>
                  <Tooltip.Provider delayDuration={200}>
                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <button disabled={submitting} className="inline-flex items-center rounded-full bg-gradient-to-b from-indigo-600 to-indigo-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:brightness-110 disabled:opacity-50 cursor-pointer">{submitting ? 'Sending…' : 'Send Invite'}</button>
                      </Tooltip.Trigger>
                      <Tooltip.Portal>
                        <Tooltip.Content side="top" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Send email and generate invite</Tooltip.Content>
                      </Tooltip.Portal>
                    </Tooltip.Root>
                  </Tooltip.Provider>
                </form>
                {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
              </div>

              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
                <h2 className="mb-2 text-lg font-semibold">Result</h2>
                {!result ? (
                  <p className="text-sm text-gray-600 dark:text-gray-400">No invite sent yet.</p>
                ) : (
                  <div className="space-y-3 text-sm">
                    <div className="grid grid-cols-[110px_1fr_auto] items-center gap-2">
                      <div className="text-gray-600 dark:text-gray-400">Code:</div>
                      <code className="font-mono bg-white/70 dark:bg-gray-800/60 rounded px-2 py-1 ring-1 ring-gray-200/70 dark:ring-gray-700/60">{result.code}</code>
                      <Tooltip.Provider>
                        <Tooltip.Root>
                          <Tooltip.Trigger asChild>
                            <button onClick={() => navigator.clipboard.writeText(result.code)} className="rounded-full px-2 py-1 text-xs ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">Copy</button>
                          </Tooltip.Trigger>
                          <Tooltip.Portal>
                            <Tooltip.Content side="left" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Copy code</Tooltip.Content>
                          </Tooltip.Portal>
                        </Tooltip.Root>
                      </Tooltip.Provider>
                    </div>
                    <div className="grid grid-cols-[110px_1fr_auto] items-center gap-2">
                      <div className="text-gray-600 dark:text-gray-400">Join URL:</div>
                      <a className="truncate text-indigo-600 hover:underline" href={result.join_url} target="_blank" rel="noreferrer">{result.join_url}</a>
                      <Tooltip.Provider>
                        <Tooltip.Root>
                          <Tooltip.Trigger asChild>
                            <button onClick={() => navigator.clipboard.writeText(result.join_url)} className="rounded-full px-2 py-1 text-xs ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">Copy</button>
                          </Tooltip.Trigger>
                          <Tooltip.Portal>
                            <Tooltip.Content side="left" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Copy join URL</Tooltip.Content>
                          </Tooltip.Portal>
                        </Tooltip.Root>
                      </Tooltip.Provider>
                    </div>
                    <div className="grid grid-cols-[110px_1fr_auto] items-center gap-2">
                      <div className="text-gray-600 dark:text-gray-400">Welcome URL:</div>
                      <a className="truncate text-indigo-600 hover:underline" href={result.welcome_url} target="_blank" rel="noreferrer">{result.welcome_url}</a>
                      <Tooltip.Provider>
                        <Tooltip.Root>
                          <Tooltip.Trigger asChild>
                            <button onClick={() => navigator.clipboard.writeText(result.welcome_url)} className="rounded-full px-2 py-1 text-xs ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">Copy</button>
                          </Tooltip.Trigger>
                          <Tooltip.Portal>
                            <Tooltip.Content side="left" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Copy welcome URL</Tooltip.Content>
                          </Tooltip.Portal>
                        </Tooltip.Root>
                      </Tooltip.Provider>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
