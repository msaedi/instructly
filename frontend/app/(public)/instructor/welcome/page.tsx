'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

function WelcomeInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [code, setCode] = useState('');
  const email = params.get('email') || '';

  useEffect(() => {
    const qp = params.get('invite_code') || '';
    if (qp) {
      setCode(qp);
      try { sessionStorage.setItem('invite_code', qp); } catch {}
    } else {
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') : '';
      if (stored) setCode(stored);
      else {
        router.replace('/instructor/join');
        return;
      }
    }
    // Validate on load to prevent stale/used/expired codes
    (async () => {
      const current = qp || (typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') || '' : '');
      const res = await fetch(`${API_BASE_URL}/api/beta/invites/validate?code=${encodeURIComponent(current)}`);
      const data = await res.json();
      if (!data.valid) {
        router.replace('/instructor/join');
      }
    })();
  }, [params, router]);

  const signupHref = `/signup?role=instructor&founding=true${code ? `&invite_code=${encodeURIComponent(code)}` : ''}${email ? `&email=${encodeURIComponent(email)}` : ''}&redirect=${encodeURIComponent('/instructor/onboarding/welcome')}`;

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-2xl">
        <div className="bg-white dark:bg-gray-800 py-10 px-8 shadow sm:rounded-lg">
          <h1 className="text-3xl font-bold text-center mb-2">Welcome to the Founding Instructor Program! 🎉</h1>
          <p className="text-center text-gray-600 dark:text-gray-300 mb-8">
            {code ? (
              <>
                Your code <span className="font-mono font-semibold">{code}</span> is valid.
              </>
            ) : (
              'Your code is valid.'
            )}
          </p>

          <div className="space-y-3 text-gray-900 dark:text-gray-100">
            <p className="font-semibold">As a founding instructor you get:</p>
            <ul className="list-none space-y-2">
              <li>✅ 0% platform fees for 60 days OR 10% for first year (you choose)</li>
              <li>✅ $25 per completed lesson (up to 8 lessons = $200 bonus)</li>
              <li>✅ Permanent &quot;Founding Instructor - NYC&quot; badge</li>
              <li>✅ $50 for maintaining 10+ hrs/week availability for 4 weeks</li>
              <li>✅ Priority placement in search results</li>
            </ul>
          </div>

          <div className="mt-8 flex justify-center">
            <Link
              href={signupHref}
              className="px-6 py-2 rounded-md text-white bg-[#6A0DAD] hover:bg-[#6A0DAD]"
            >
              Become a Founding Instructor
            </Link>
          </div>

          <div className="mt-8 text-center text-sm text-gray-600 dark:text-gray-300">
            <p>Questions? Email <a className="underline" href="mailto:founders@instainstru.com">founders@instainstru.com</a></p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function InstructorWelcomePage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center p-6">Loading…</div>}>
      <WelcomeInner />
    </Suspense>
  );
}
