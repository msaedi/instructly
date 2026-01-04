'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Script from 'next/script';
import { Check as CheckIcon } from 'lucide-react';
import { httpGet } from '@/lib/http';

function WelcomeInner() {
  const params = useSearchParams();
  const rawInviteCode = params.get('invite_code') || '';
  const email = params.get('email') || '';
  const [code] = useState(() => {
    if (typeof window === 'undefined') {
      return '';
    }
    const normalized = rawInviteCode ? rawInviteCode.toUpperCase() : '';
    const stored = sessionStorage.getItem('invite_code') || '';
    const resolved = normalized || stored;
    if (resolved) {
      try {
        sessionStorage.setItem('invite_code', resolved);
      } catch {}
    }
    return resolved;
  });

  useEffect(() => {
    let cancelled = false;

    const redirectToJoin = () => {
      const joinUrl = new URL('/instructor/join', window.location.origin);
      const redirectCode =
        rawInviteCode || (typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') || '' : '');
      if (redirectCode) joinUrl.searchParams.set('invite_code', redirectCode);
      if (email) joinUrl.searchParams.set('email', email);
      window.location.replace(joinUrl.toString());
    };

    const ensureVerified = async () => {
      try {
        await httpGet('/api/v1/beta/invites/verified');

        const current =
          rawInviteCode || (typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') || '' : '');
        if (!current) {
          redirectToJoin();
          return;
        }

        if (!cancelled) {
          try { sessionStorage.setItem('invite_code', current); } catch {}
        }
      } catch {
        redirectToJoin();
      }
    };

    void ensureVerified();

    return () => {
      cancelled = true;
    };
  }, [email, rawInviteCode]);

  const signupHref = `/signup?role=instructor&founding=true${code ? `&invite_code=${encodeURIComponent(code)}` : ''}${email ? `&email=${encodeURIComponent(email)}` : ''}&redirect=${encodeURIComponent('/instructor/onboarding/welcome')}`;

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 cursor-default">
      <div className="sm:mx-auto sm:w-full sm:max-w-2xl">
        <div className="bg-white dark:bg-gray-800 py-10 px-8 shadow sm:rounded-lg">
          <div className="text-center mb-4">
            <h1 className="text-3xl font-bold tracking-tight text-[#7E22CE]">{`iNSTAiNSTRU`}</h1>
            <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mt-4">
              Welcome to the Founding Instructor Program
            </p>
            <div className="h-px w-full bg-gradient-to-r from-transparent via-[#7E22CE] to-transparent mt-4" />
          </div>
          <div className="text-center text-gray-600 dark:text-gray-300 mb-6 space-y-2">
            <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              We’re thrilled to have you on iNSTAiNSTRU
            </p>
            <p className="text-base">
              Over 500 students searched for instructors in your area this week.
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Next up, create your profile so you’re launch-ready; we’ll alert you the moment booking goes live!
            </p>
          </div>

          <div className="space-y-4 text-gray-900 dark:text-gray-100 text-left">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Founding Instructor Perks</h2>

            <div className="space-y-4">
              <div className="flex gap-3">
                <CheckIcon className="w-5 h-5 text-purple-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900">Lifetime Lowest Rate</h3>
                  <p className="text-gray-600 text-sm">
                    Lock in our lowest rate—permanently. Whatever the floor is, you&apos;re on it. Forever.
                    Currently that&apos;s 8%. Standard instructors start at 15% and work their way down. You don&apos;t.
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <CheckIcon className="w-5 h-5 text-purple-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900">Founding Instructor Badge</h3>
                  <p className="text-gray-600 text-sm">
                    A Founding Instructor badge on your profile marks you as one of the first 100.
                    It can&apos;t be achieved later.
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <CheckIcon className="w-5 h-5 text-purple-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900">Priority Visibility</h3>
                  <p className="text-gray-600 text-sm">
                    Higher placement in search results during our NYC launch. More visibility means
                    more bookings while we grow together.
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <CheckIcon className="w-5 h-5 text-purple-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900">Availability Commitment</h3>
                  <p className="text-gray-600 text-sm">
                    Founding Instructors commit to posting availability—10 hours per week, across 3+ days,
                    during 8am–8pm. This ensures students always find real options when they search.
                  </p>
                </div>
              </div>
            </div>

            <p className="text-sm text-gray-600 italic mt-6">
              Only 100 founding instructors will ever exist.
            </p>
          </div>

          <div className="mt-6 flex justify-center">
            <Link
              href={signupHref}
              className="px-6 py-2 rounded-md text-white bg-[#7E22CE] hover:bg-[#7E22CE]"
            >
              Become a Founding Instructor
            </Link>
          </div>

          <div className="mt-4 text-center text-sm text-gray-600 dark:text-gray-300">
            <p className="text-sm text-gray-500">
              Have questions? Email us at{' '}
              <a href="mailto:hello@instainstru.com" className="text-purple-600 hover:underline">
                hello@instainstru.com
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function InstructorWelcomePage() {
  return (
    <>
      <Suspense fallback={<div className="min-h-screen flex items-center justify-center p-6">Loading…</div>}>
        <WelcomeInner />
      </Suspense>
      <Script
        id="vtag-ai-js"
        src="https://r2.leadsy.ai/tag.js"
        data-pid="UyudE5UkciQokTPX"
        data-version="062024"
        strategy="afterInteractive"
      />
    </>
  );
}
