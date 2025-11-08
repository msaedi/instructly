'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { withApiBase } from '@/lib/apiBase';
import { copyToClipboard } from '@/lib/copy';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import * as Tooltip from '@radix-ui/react-tooltip';
import * as Select from '@radix-ui/react-select';
import { ChevronDown, Check } from 'lucide-react';

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
  const [betaSummary, setBetaSummary] = useState<{ phase: string; invites24h: number; errors24h: number } | null>(null);
  const [csvText, setCsvText] = useState('');
  const [asyncTaskId, setAsyncTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ state: string; current: number; total: number; sent: number; failed: number; sent_items?: { id: string; code: string; email: string; join_url: string; welcome_url: string }[]; failed_items?: { email: string; reason: string }[] } | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  // Cookies carry auth; avoid localStorage for security and SSR safety

  useEffect(() => {
    async function fetchSummary() {
      try {
        const [settingsRes, summaryRes] = await Promise.all([
          fetch(withApiBase(`/api/beta/settings`), { credentials: 'include' }),
          fetch(withApiBase(`/api/beta/metrics/summary`), { credentials: 'include' }),
        ]);
        const settings = settingsRes.ok ? await settingsRes.json() : null;
        const phase = settings?.beta_phase || 'unknown';
        const data = summaryRes.ok ? await summaryRes.json() : { invites_sent_24h: 0, invites_errors_24h: 0 };
        setBetaSummary({ phase, invites24h: data.invites_sent_24h || 0, errors24h: data.invites_errors_24h || 0 });
      } catch {
        setBetaSummary(null);
      }
    }
    void fetchSummary();
  }, []);

  useEffect(() => {
    if (!asyncTaskId) return;
    let cancelled = false;
    async function poll() {
      try {
        const res = await fetch(withApiBase(`/api/beta/invites/send-batch-progress?task_id=${encodeURIComponent(asyncTaskId || '')}`), { credentials: 'include' });
        if (!res.ok) throw new Error('progress error');
        const data = await res.json();
        if (!cancelled) {
          setProgress({ state: data.state, current: data.current, total: data.total, sent: data.sent, failed: data.failed });
          if (data.state === 'SUCCESS' || data.state === 'FAILURE') return; // stop
          setTimeout(() => { void poll(); }, 1500);
        }
      } catch {
        if (!cancelled) setTimeout(() => { void poll(); }, 2000);
      }
    }
    void poll();
    return () => { cancelled = true; };
  }, [asyncTaskId]);

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
      const res = await fetch(withApiBase(`/api/beta/invites/send`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_email: email, role, expires_in_days: days, source }),
        credentials: 'include',
      });
      if (!res.ok) throw new Error((await res.text()) || `Failed to send invite (${res.status})`);
      const data = await res.json();
      setResult({ code: data.code, join_url: data.join_url, welcome_url: data.welcome_url });
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed';
      setError(errorMessage);
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
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>
          <section className="col-span-12 md:col-span-9 lg:col-span-9">
            <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Beta summary card - order 4 */}
              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur order-4">
                <h2 className="mb-2 text-lg font-semibold">Beta Summary</h2>
                {!betaSummary ? (
                  <p className="text-sm text-gray-600 dark:text-gray-400">Loading summary…</p>
                ) : (
                  <div className="grid grid-cols-3 gap-3 text-sm">
                    <div>
                      <div className="text-gray-600 dark:text-gray-400">Phase</div>
                      <div className="font-medium">{betaSummary.phase}</div>
                    </div>
                    <div>
                      <div className="text-gray-600 dark:text-gray-400">Invites (24h)</div>
                      <div className="font-medium">{betaSummary.invites24h}</div>
                    </div>
                    <div>
                      <div className="text-gray-600 dark:text-gray-400">Errors (24h)</div>
                      <div className="font-medium">{betaSummary.errors24h}</div>
                    </div>
                  </div>
                )}
              </div>
              {/* Send invite - order 1 */}
              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur order-1">
                <h2 className="mb-2 text-lg font-semibold">Send Founding Instructor Invite</h2>
                <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">Generate an invite code and email a direct link to onboarding. Links include both Join and Welcome URLs.</p>
                <form onSubmit={onSubmit} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Email</label>
                    <input
                      data-testid="invite-email-input"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      type="email"
                      className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800"
                      placeholder="instructor@example.com"
                    />
                  </div>
                  <div className="grid grid-cols-12 gap-3 items-end">
                    <div className="col-span-6 min-w-0">
                      <label className="block text-sm font-medium mb-1">Role</label>
                      <Select.Root value={role} onValueChange={setRole}>
                        <Select.Trigger className="inline-flex items-center justify-between w-full rounded-lg px-3 py-2 ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 whitespace-nowrap overflow-hidden text-ellipsis min-w-0">
                          <Select.Value className="truncate" />
                          <Select.Icon className="ml-2 shrink-0">
                            <ChevronDown className="h-4 w-4 text-gray-500" />
                          </Select.Icon>
                        </Select.Trigger>
                        <Select.Portal>
                          <Select.Content className="overflow-hidden rounded-md bg-white dark:bg-gray-800 shadow ring-1 ring-gray-200 dark:ring-gray-700">
                            <Select.Viewport className="p-1">
                              <Select.Item value="instructor_beta" className="relative flex select-none items-center rounded px-2 py-1.5 text-sm text-gray-800 dark:text-gray-200 data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-700 outline-none cursor-pointer">
                                <Select.ItemText>instructor_beta</Select.ItemText>
                                <Select.ItemIndicator className="absolute right-2">
                                  <Check className="h-4 w-4" />
                                </Select.ItemIndicator>
                              </Select.Item>
                            </Select.Viewport>
                          </Select.Content>
                        </Select.Portal>
                      </Select.Root>
                    </div>
                    <div className="col-span-3">
                      <label className="block text-sm font-medium mb-1">Expires (days)</label>
                      <input value={days} onChange={(e) => setDays(parseInt(e.target.value || '14', 10))} min={1} max={180} type="number" className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800" />
                    </div>
                    <div className="col-span-3">
                      <label className="block text-sm font-medium mb-1">Source</label>
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

              {/* Result - order 2 */}
              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur order-2">
                <h2 className="mb-2 text-lg font-semibold">Result</h2>
                {!result ? (
                  <p className="text-sm text-gray-600 dark:text-gray-400">No invite sent yet.</p>
                ) : (
                  <div className="space-y-3 text-sm">
                    <div className="grid grid-cols-[110px_1fr_auto] items-center gap-2">
                      <div className="text-gray-600 dark:text-gray-400">Code:</div>
                      <code
                        data-testid="invite-code-value"
                        className="font-mono bg-white/70 dark:bg-gray-800/60 rounded px-2 py-1 ring-1 ring-gray-200/70 dark:ring-gray-700/60"
                      >
                        {result.code}
                      </code>
                      <Tooltip.Provider>
                        <Tooltip.Root>
                          <Tooltip.Trigger asChild>
                            <button onClick={() => { void copyToClipboard(result.code); }} className="rounded-full px-2 py-1 text-xs ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">Copy</button>
                          </Tooltip.Trigger>
                          <Tooltip.Portal>
                            <Tooltip.Content side="left" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Copy code</Tooltip.Content>
                          </Tooltip.Portal>
                        </Tooltip.Root>
                      </Tooltip.Provider>
                    </div>
                    <div className="grid grid-cols-[150px_1fr_auto] items-center gap-2">
                      <div className="text-gray-600 dark:text-gray-400">User link (canonical):</div>
                      <a className="truncate text-indigo-600 hover:underline" href={result.join_url} target="_blank" rel="noreferrer">{result.join_url}</a>
                      <Tooltip.Provider>
                        <Tooltip.Root>
                          <Tooltip.Trigger asChild>
                            <button onClick={() => { void copyToClipboard(result.join_url); }} className="rounded-full px-2 py-1 text-xs ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">Copy</button>
                          </Tooltip.Trigger>
                          <Tooltip.Portal>
                            <Tooltip.Content side="left" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Copy join URL</Tooltip.Content>
                          </Tooltip.Portal>
                        </Tooltip.Root>
                      </Tooltip.Provider>
                    </div>
                    <div className="grid grid-cols-[150px_1fr_auto] items-center gap-2">
                      <div className="text-gray-600 dark:text-gray-400">Resume link (support):</div>
                      <a className="truncate text-indigo-600 hover:underline" href={result.welcome_url} target="_blank" rel="noreferrer">{result.welcome_url}</a>
                      <Tooltip.Provider>
                        <Tooltip.Root>
                          <Tooltip.Trigger asChild>
                            <button onClick={() => { void copyToClipboard(result.welcome_url); }} className="rounded-full px-2 py-1 text-xs ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">Copy</button>
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

              {/* CSV bulk invites - order 3 */}
              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur order-3">
                <h2 className="mb-2 text-lg font-semibold">CSV Bulk Invites</h2>
                <p className="mb-3 text-sm text-gray-600 dark:text-gray-400">Paste a CSV of emails (one per line or comma-separated). This will generate invites without sending emails.</p>
                <textarea
                  value={csvText}
                  onChange={(e) => setCsvText(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 min-h-[120px]"
                  placeholder="alice@example.com\nbob@example.com\ncharlie@example.com"
                />
                <div className="mt-3 flex gap-2">
                  <button
                    className="inline-flex items-center rounded-full bg-gradient-to-b from-indigo-600 to-indigo-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:brightness-110 disabled:opacity-50 cursor-pointer"
                    onClick={async () => {
                      setError(null);
                      const emails = csvText
                        .split(/\n|,|;|\s+/)
                        .map((s) => s.trim())
                        .filter((s) => s.length > 0);
                      if (emails.length === 0) return;
                      try {
                        const res = await fetch(withApiBase('/api/beta/invites/generate'), {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ count: emails.length, role, expires_in_days: days, source: 'csv_upload', emails }),
                          credentials: 'include',
                        });
                        if (!res.ok) throw new Error((await res.text()) || `Failed to generate invites (${res.status})`);
                        const data = await res.json();
                        // Show a simple success summary
                        setResult({ code: data.invites?.[0]?.code || 'bulk', join_url: '#', welcome_url: '#' });
                      } catch (err: unknown) {
                        const errorMessage = err instanceof Error ? err.message : 'Failed to generate invites';
                        setError(errorMessage);
                      }
                    }}
                  >
                    Generate Invites
                  </button>
                  <button
                    className="inline-flex items-center rounded-full bg-gradient-to-b from-green-600 to-green-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:brightness-110 disabled:opacity-50 cursor-pointer"
                    onClick={async () => {
                      setError(null);
                      const emails = csvText
                        .split(/\n|,|;|\s+/)
                        .map((s) => s.trim())
                        .filter((s) => s.length > 0);
                      if (emails.length === 0) return;
                      try {
                        const r = await fetch(withApiBase('/api/beta/invites/send-batch-async'), {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ emails, role, expires_in_days: days, source: 'csv_upload' }),
                          credentials: 'include',
                        });
                        if (!r.ok) throw new Error((await r.text()) || `Failed to send batch invites (${r.status})`);
                        const data = await r.json();
                        setAsyncTaskId(data.task_id);
                        setProgress({ state: 'PENDING', current: 0, total: emails.length, sent: 0, failed: 0 });
                      } catch (err: unknown) {
                        const errorMessage = err instanceof Error ? err.message : 'Failed to send batch invites';
                        setError(errorMessage);
                      }
                    }}
                  >
                    Send Emails
                  </button>
                  {progress && (
                    <div className="ml-2 text-xs text-gray-600 dark:text-gray-400">
                      <div className="mb-1">
                        <span className="font-medium">Batch:</span> {progress.state} — {progress.current}/{progress.total} processed · sent {progress.sent}, failed {progress.failed}
                      </div>
                      <div className="h-2 w-full bg-gray-200 dark:bg-gray-800 rounded overflow-hidden">
                        <div
                          className="h-full bg-indigo-500"
                          style={{ width: `${progress.total ? Math.round((progress.current / progress.total) * 100) : 0}%` }}
                        />
                      </div>
                      {(progress.sent_items?.length || progress.failed_items?.length) ? (
                        <div className="mt-2">
                          <button
                            className="underline text-indigo-600 dark:text-indigo-400 cursor-pointer"
                            onClick={() => setShowDetails((v) => !v)}
                          >
                            {showDetails ? 'Hide' : 'Show'} details
                          </button>
                          {showDetails && (
                            <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                              <div className="rounded-lg p-2 ring-1 ring-gray-200 dark:ring-gray-700 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
                                <div className="font-medium mb-1">Sent</div>
                                <div className="max-h-40 overflow-auto text-[11px] space-y-1">
                                  {progress.sent_items?.map((it) => (
                                    <div key={it.id} className="flex items-center justify-between gap-2">
                                      <div className="truncate">{it.email} — <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{it.code}</code></div>
                                      <div className="flex gap-1">
                                        <button onClick={() => { void copyToClipboard(it.code); }} className="px-1 py-0.5 rounded ring-1 ring-gray-300 dark:ring-gray-700">Copy code</button>
                                        <button onClick={() => { void copyToClipboard(it.join_url); }} className="px-1 py-0.5 rounded ring-1 ring-gray-300 dark:ring-gray-700">Copy user link</button>
                                      </div>
                                    </div>
                                  ))}
                                  {!progress.sent_items?.length && <div className="text-gray-500">None</div>}
                                </div>
                              </div>
                              <div className="rounded-lg p-2 ring-1 ring-gray-200 dark:ring-gray-700 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
                                <div className="font-medium mb-1">Failed</div>
                                <div className="max-h-40 overflow-auto text-[11px] space-y-1">
                                  {progress.failed_items?.map((it, idx) => (
                                    <div key={`${it.email}-${idx}`} className="flex items-center justify-between gap-2">
                                      <div className="truncate">{it.email}</div>
                                      <div className="text-red-600 dark:text-red-400 truncate">{it.reason}</div>
                                    </div>
                                  ))}
                                  {!progress.failed_items?.length && <div className="text-gray-500">None</div>}
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
