'use client';

import { useEffect, useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import { createStripeIdentitySession, createSignedUpload, getConnectStatus } from '@/lib/api';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';

export default function Step4Verification() {
  const [identityLoading, setIdentityLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [fileInfo, setFileInfo] = useState<{ name: string; size: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectStatus, setConnectStatus] = useState<{
    has_account: boolean;
    onboarding_completed: boolean;
    charges_enabled: boolean;
    payouts_enabled: boolean;
    details_submitted: boolean;
  } | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const status = await getConnectStatus();
        setConnectStatus(status);
      } catch (e) {
        logger.warn('Failed to load connect status');
      }
    };
    void load();
  }, []);

  const startIdentity = async () => {
    try {
      setIdentityLoading(true);
      setError(null);
      const session = await createStripeIdentitySession();
      // Prefer Stripe.js modal to avoid brittle hosted-link flows
      try {
        const publishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
        if (publishableKey) {
          const stripe = await loadStripe(publishableKey);
          if (!stripe) throw new Error('Failed to load Stripe.js');
          const result = await stripe.verifyIdentity(session.client_secret);
          if (result?.error) {
            setError(result.error.message || 'Verification could not be started');
            return;
          }
          // On completion or dismissal, take user to status
          window.location.href = '/instructor/onboarding/status?identity_return=true';
          return;
        }
      } catch (e) {
        // Fallback to hosted link
      }
      window.location.href = `https://verify.stripe.com/start/${session.client_secret}`;
    } catch (e) {
      logger.error('Identity start failed', e);
      setError('Failed to start ID verification');
    } finally {
      setIdentityLoading(false);
    }
  };

  const onFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null);
    setUploading(true);
    try {
      const signed = await createSignedUpload({
        filename: f.name,
        content_type: f.type || 'application/octet-stream',
        size_bytes: f.size,
        purpose: 'background_check',
      });
      const putRes = await fetch(signed.upload_url, {
        method: 'PUT',
        headers: signed.headers,
        body: f,
      });
      if (!putRes.ok) throw new Error('Upload failed');
      setFileInfo({ name: f.name, size: f.size });
    } catch (err) {
      logger.error('Upload failed', err);
      setError('Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full relative">
          <a href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </a>

          {/* Progress Bar - 4 Steps - Absolutely centered */}
          <div className="absolute left-1/2 transform -translate-x-1/2 flex items-center gap-0">
            {/* Step 1 - Completed */}
            <div className="flex items-center">
              <button
                onClick={() => {/* TODO: Navigate to Step 1 */}}
                className="w-6 h-6 rounded-full bg-purple-600 flex items-center justify-center hover:bg-purple-700 transition-colors cursor-pointer"
                title="Step 1: Account Created"
              >
                <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                </svg>
              </button>
              <div className="w-60 h-0.5 bg-purple-600"></div>
            </div>

            {/* Step 2 - Completed */}
            <div className="flex items-center">
              <button
                onClick={() => window.location.href = '/instructor/onboarding/skill-selection'}
                className="w-6 h-6 rounded-full bg-purple-600 flex items-center justify-center hover:bg-purple-700 transition-colors cursor-pointer"
                title="Step 2: Skills & Pricing"
              >
                <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                </svg>
              </button>
              <div className="w-60 h-0.5 bg-purple-600"></div>
            </div>

            {/* Step 3 - Current (Verification) */}
            <div className="flex items-center">
              <button
                onClick={() => {/* Already on this page */}}
                className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                title="Step 3: Verification (Current)"
              ></button>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 4 - Upcoming */}
            <div className="flex items-center">
              <button
                onClick={() => window.location.href = '/instructor/onboarding/status'}
                className="w-6 h-6 rounded-full border-2 border-gray-300 hover:border-gray-400 transition-colors cursor-pointer"
                title="Step 4: Status"
              ></button>
            </div>
          </div>

          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <h1 className="text-3xl font-bold text-gray-600 mb-2">Build trust with students</h1>
          <p className="text-gray-600">Get verified and start teaching today</p>
        </div>
      <div className="mt-4 rounded-2xl ring-1 ring-gray-100 shadow-sm p-4 bg-white">
        <h2 className="text-sm font-medium text-gray-900">Status</h2>
        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <StatusRow label="Stripe Connect" ok={!!connectStatus?.onboarding_completed} />
          <StatusRow label="Payments enabled" ok={!!connectStatus?.charges_enabled} />
          <StatusRow label="ID verification started" ok={identityLoading || false /* optimistic while redirecting */} />
          <StatusRow label="Background check uploaded" ok={!!fileInfo} />
        </div>
      </div>


      {error && <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">{error}</div>}

      <div className="mt-6 grid gap-6">
        <div className="rounded-2xl ring-1 ring-gray-100 shadow-sm p-5 bg-white">
          <h2 className="text-lg font-medium text-gray-900">Basic ID Verification</h2>
          <p className="text-gray-600 mt-1">Government ID + quick selfie. Usually 5 minutes.</p>
          <button
            onClick={startIdentity}
            disabled={identityLoading}
            className="mt-3 inline-flex items-center px-5 py-2.5 rounded-lg text-white bg-[#6A0DAD] hover:bg-[#5c0a9a] disabled:opacity-50 shadow-sm"
          >
            {identityLoading ? 'Starting…' : 'Start ID Verification'}
          </button>
        </div>

        <div className="rounded-2xl ring-1 ring-gray-100 shadow-sm p-5 bg-white">
          <h2 className="text-lg font-medium text-gray-900">Upload Background Check</h2>
          <p className="text-gray-600 mt-1">PDF/JPG/PNG, max 10MB. From approved providers like Checkr, Sterling, NYC DOE.</p>
          <div className="mt-3">
            <label className="inline-flex items-center px-4 py-2.5 rounded-lg bg-purple-50 border border-purple-300 text-purple-700 font-medium shadow-sm hover:bg-purple-100 transition-colors cursor-pointer">
              <input type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden" onChange={onFileSelected} />
              <span>{uploading ? 'Uploading…' : 'Choose File'}</span>
            </label>
            {fileInfo && (
              <div className="mt-2 text-sm text-gray-700">Selected: {fileInfo.name}</div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-8">
        <button
          className="px-5 py-2.5 rounded-lg text-white bg-[#6A0DAD] hover:bg-[#5c0a9a] shadow-sm"
          onClick={() => (window.location.href = '/instructor/onboarding/status')}
        >
          Continue
        </button>
      </div>
      </div>
    </div>
  );
}

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-gray-700">{label}</span>
      <span className={ok ? 'text-green-600' : 'text-gray-400'}>{ok ? '✓' : '•'}</span>
    </div>
  );
}
