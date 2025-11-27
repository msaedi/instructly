'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { httpGet } from '@/lib/http';

function WelcomeInner() {
  const params = useSearchParams();
  const [code, setCode] = useState('');
  const email = params.get('email') || '';

  useEffect(() => {
    const rawParam = params.get('invite_code') || '';
    const qp = rawParam ? rawParam.toUpperCase() : '';
    if (qp) {
      setCode(qp);
      try { sessionStorage.setItem('invite_code', qp); } catch {}
    } else {
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') : '';
      if (stored) setCode(stored);
    }

    let cancelled = false;

    const redirectToJoin = () => {
      const joinUrl = new URL('/instructor/join', window.location.origin);
      const redirectCode = rawParam || (typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') || '' : '');
      if (redirectCode) joinUrl.searchParams.set('invite_code', redirectCode);
      if (email) joinUrl.searchParams.set('email', email);
      window.location.replace(joinUrl.toString());
    };

    const ensureVerified = async () => {
      try {
        await httpGet('/api/v1/beta/invites/verified');

        const current = qp || (typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') || '' : '');
        if (!current) {
          redirectToJoin();
          return;
        }

        if (!cancelled) {
          setCode(current);
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
  }, [email, params]);

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

          <div className="space-y-3 text-gray-900 dark:text-gray-100 text-left">
            <p className="text-lg font-semibold text-gray-800 dark:text-gray-200">Founding Instructor Perks</p>
            <ul className="space-y-3">
              {[
                {
                  title: 'Lifetime 8% Platform Fee',
                  detail: 'Founding Instructors lock in our lowest commission rate—just 8%, guaranteed for life.',
                },
                {
                  title: 'Skip the Higher Tiers',
                  detail: 'Founding Instructors permanently bypass the 15% and 12% commission tiers.',
                },
                {
                  title: 'No Activity Requirements',
                  detail: 'No rolling 30-day thresholds, no step-downs, and no inactivity penalties.',
                },
                {
                  title: 'All Standard Benefits Included',
                  detail: 'Instant bookings, secure Stripe payments, verified-background badge, reviews & ratings, wallet credits, and referral rewards—all included from day one.',
                },
              ].map((perk) => (
                <li key={perk.title} className="flex items-start gap-2">
                  <span className="mt-1 text-[#7E22CE]" aria-hidden="true">✓</span>
                  <div>
                    <p className="text-sm font-semibold">{perk.title}</p>
                    <p className="text-xs text-gray-600 dark:text-gray-300 leading-snug">{perk.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="text-xs text-gray-500">
              Perks apply once onboarding is complete. Limited to the first 100 Founding Instructors.
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
            <p className="text-xs text-gray-500">
              Need the fine print?{' '}
              <a className="text-[#7E22CE] hover:underline" href="/legal">
                See perk details
              </a>
              .
            </p>
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
