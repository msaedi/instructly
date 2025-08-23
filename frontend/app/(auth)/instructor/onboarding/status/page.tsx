'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { getConnectStatus } from '@/lib/api';
import { logger } from '@/lib/logger';

export default function OnboardingStatusPage() {
  const [connectStatus, setConnectStatus] = useState<any>(null);

  useEffect(() => {
    (async () => {
      try {
        const s = await getConnectStatus();
        setConnectStatus(s);
      } catch (e) {
        logger.warn('Failed to load connect status');
      }
    })();
  }, []);

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-semibold text-[#6A0DAD]">Onboarding Status</h1>
      <p className="text-gray-600 mt-1">Finish these steps to go live.</p>

      <div className="mt-6 space-y-4">
        <Row label="Stripe Connect" ok={!!connectStatus?.onboarding_completed} action={<Link href="/instructor/dashboard" className="text-purple-700 hover:underline">Open dashboard</Link>} />
        <Row label="ID verification" ok={false} action={<Link href="/instructor/onboarding/step-4" className="text-purple-700 hover:underline">Start</Link>} />
        <Row label="Background check" ok={false} action={<Link href="/instructor/onboarding/step-4" className="text-purple-700 hover:underline">Upload</Link>} />
        <Row label="Skills & pricing" ok={false} action={<Link href="/instructor/onboarding/step-3" className="text-purple-700 hover:underline">Edit</Link>} />
      </div>
    </div>
  );
}

function Row({ label, ok, action }: { label: string; ok: boolean; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border border-gray-100 rounded-md px-4 py-3 bg-white shadow-sm">
      <div className="text-gray-800">{label}</div>
      <div className={ok ? 'text-green-600' : 'text-gray-400'}>{ok ? '✓' : '•'}</div>
      <div>{action}</div>
    </div>
  );
}
