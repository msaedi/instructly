'use client';

import { useEffect, useState } from 'react';
import { createStripeIdentitySession, createSignedUpload, getConnectStatus } from '@/lib/api';
import { logger } from '@/lib/logger';

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
      // Redirect to Stripe Identity modal URL via client JS SDK is preferred;
      // for now we use the client_secret with hosted flow fallback
      // If you later include Stripe Identity JS, swap this redirect with open() method.
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
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-semibold text-[#6A0DAD]">Build trust with students</h1>
      <p className="text-gray-600 mt-1">Get verified and start teaching today</p>
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
            <label className="inline-flex items-center px-4 py-2 rounded-lg bg-white border border-gray-200 shadow-sm hover:bg-gray-50 cursor-pointer">
              <input type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden" onChange={onFileSelected} />
              <span className="text-gray-800">{uploading ? 'Uploading…' : 'Choose file'}</span>
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
          onClick={() => (window.location.href = '/instructor/dashboard')}
        >
          Continue to dashboard
        </button>
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
